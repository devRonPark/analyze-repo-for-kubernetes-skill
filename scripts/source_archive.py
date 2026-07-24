#!/usr/bin/env python3
"""Safely extract a source archive into a disposable analysis directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath


class ArchiveError(ValueError):
    """Raised when an archive is not a safe source input."""


MAX_MEMBER_COUNT = 10_000
MAX_UNCOMPRESSED_BYTES = 1_073_741_824
WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:/")


def archive_format(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".zip"):
        return "zip"
    if name.endswith(".tar.gz") or name.endswith(".tgz"):
        return "tar.gz"
    raise ArchiveError("지원하는 source archive 형식은 .zip, .tar.gz, .tgz뿐입니다")


def require_regular_archive(path: Path) -> Path:
    requested = path.expanduser()
    try:
        info = requested.lstat()
    except FileNotFoundError as error:
        raise ArchiveError("source archive path가 존재하지 않습니다") from error
    if requested.is_symlink() or not stat.S_ISREG(info.st_mode):
        raise ArchiveError("source archive는 symlink가 아닌 일반 파일이어야 합니다")
    if not os.access(requested, os.R_OK):
        raise ArchiveError("source archive를 읽을 수 없습니다")
    return requested.resolve(strict=True)


def safe_member_path(name: str) -> Path:
    normalized = name.replace("\\", "/")
    if not normalized or "\x00" in normalized or WINDOWS_DRIVE_PATH.match(normalized):
        raise ArchiveError("archive member path가 올바르지 않습니다")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ArchiveError("archive member가 extraction directory 밖을 가리킵니다")
    parts = [part for part in path.parts if part not in (".", "")]
    if not parts:
        raise ArchiveError("archive member path가 올바르지 않습니다")
    return Path(*parts)


def validate_limits(member_count: int, total_size: int) -> None:
    if member_count > MAX_MEMBER_COUNT:
        raise ArchiveError(f"archive member 수가 한도({MAX_MEMBER_COUNT})를 초과합니다")
    if total_size > MAX_UNCOMPRESSED_BYTES:
        raise ArchiveError("archive의 uncompressed size가 안전 한도를 초과합니다")


def zip_members(archive: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, Path]]:
    infos = archive.infolist()
    total_size = 0
    members: list[tuple[zipfile.ZipInfo, Path]] = []
    names: set[Path] = set()
    for info in infos:
        member_path = safe_member_path(info.filename)
        mode = info.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if kind == stat.S_IFLNK:
            raise ArchiveError("symlink archive member는 허용하지 않습니다")
        is_directory = info.is_dir()
        if kind and kind not in (stat.S_IFREG, stat.S_IFDIR):
            raise ArchiveError("일반 파일과 directory 이외의 archive member는 허용하지 않습니다")
        if is_directory != (kind == stat.S_IFDIR) and kind:
            raise ArchiveError("archive member type이 일관되지 않습니다")
        if member_path in names:
            raise ArchiveError("중복 archive member path는 허용하지 않습니다")
        names.add(member_path)
        if not is_directory:
            total_size += info.file_size
        members.append((info, member_path))
    validate_limits(len(members), total_size)
    return members


def tar_members(archive: tarfile.TarFile) -> list[tuple[tarfile.TarInfo, Path]]:
    infos = archive.getmembers()
    total_size = 0
    members: list[tuple[tarfile.TarInfo, Path]] = []
    names: set[Path] = set()
    for info in infos:
        member_path = safe_member_path(info.name)
        if not (info.isreg() or info.isdir()):
            raise ArchiveError("일반 파일과 directory 이외의 archive member는 허용하지 않습니다")
        if member_path in names:
            raise ArchiveError("중복 archive member path는 허용하지 않습니다")
        names.add(member_path)
        if info.isreg():
            total_size += info.size
        members.append((info, member_path))
    validate_limits(len(members), total_size)
    return members


def output_path(root: Path, member_path: Path) -> Path:
    candidate = root / member_path
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ArchiveError("archive member가 extraction directory 밖을 가리킵니다") from error
    return candidate


def extract_zip(archive_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        members = zip_members(archive)
        for info, member_path in members:
            target = output_path(destination, member_path)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise ArchiveError("archive member path가 기존 파일과 충돌합니다")
            with archive.open(info, "r") as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)


def extract_tar(archive_path: Path, destination: Path) -> None:
    with tarfile.open(archive_path, mode="r:*") as archive:
        members = tar_members(archive)
        for info, member_path in members:
            target = output_path(destination, member_path)
            if info.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise ArchiveError("archive member path가 기존 파일과 충돌합니다")
            source = archive.extractfile(info)
            if source is None:
                raise ArchiveError("archive member를 읽을 수 없습니다")
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_extracted_root(destination: Path) -> tuple[str, Path, list[str]]:
    children = sorted(destination.iterdir(), key=lambda path: path.name)
    if not children:
        raise ArchiveError("source archive가 비어 있습니다")
    root_files = [child for child in children if child.is_file()]
    root_directories = [child for child in children if child.is_dir()]
    if root_files or len(root_directories) == 1:
        root = root_directories[0] if not root_files and len(root_directories) == 1 else destination
        return ("resolved", root, [])
    return ("awaiting_subdirectory", destination, [child.name for child in root_directories])


def extract_source_archive(archive: Path, destination: Path) -> dict[str, object]:
    archive_path = require_regular_archive(archive)
    kind = archive_format(archive_path)
    if destination.exists() or destination.is_symlink():
        raise ArchiveError("destination은 존재하지 않는 disposable directory여야 합니다")
    destination.mkdir(parents=True)
    destination = destination.resolve(strict=True)
    try:
        if kind == "zip":
            extract_zip(archive_path, destination)
        else:
            extract_tar(archive_path, destination)
        state, root, candidates = resolve_extracted_root(destination)
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise ArchiveError("source archive를 안전하게 추출할 수 없습니다") from error

    base = {
        "source_method": "source_archive",
        "target_type": "Source archive",
        "archive_path": str(archive_path),
        "archive_format": kind,
        "archive_sha256": sha256(archive_path),
        "resolved_target": str(root),
        "access_method": "safe read-only archive extraction",
    }
    if state == "awaiting_subdirectory":
        return {
            **base,
            "state": state,
            "candidate_subdirectories": candidates,
            "next_prompt": "분석할 source archive 하위 디렉터리를 선택해 주세요.",
        }
    return {
        **base,
        "state": state,
        "revision": f"archive-sha256:{base['archive_sha256']}",
        "subdirectory": str(root.relative_to(destination)) or ".",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="source archive를 안전하게 추출하고 분석 루트를 결정합니다.")
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(extract_source_archive(args.archive, args.destination), ensure_ascii=False, sort_keys=True))
        return 0
    except ArchiveError as error:
        print(f"실패: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
