from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from typing import Callable, Iterable, Iterator, Mapping

from report_lifecycle import ReportLifecycle
from report_session_service import StartCommand
from report_work_units import AnalysisSnapshot


MAX_TARGET_BYTES = 1_048_576
MAX_SNAPSHOT_BYTES = 262_144
MAX_SNAPSHOT_IDENTIFIERS = 4_096
MAX_IDENTIFIER_CHARS = 256
SNAPSHOT_KEYS = frozenset(
    ("mode", "deployable_subject_ids", "relationship_edge_ids")
)
MODES = frozenset(("summary", "detailed"))
SHA256 = re.compile(r"^[a-f0-9]{64}$")


class HandoffError(ValueError):
    pass


OpenFaultHook = Callable[[str, str], None]
DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
FILE_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)


@dataclass(frozen=True)
class VerifiedFile:
    identity: Path
    relative_parts: tuple[str, ...]
    content: bytes


def _canonical_bytes(payload: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _safe_parts(path: Path) -> tuple[str, ...]:
    parts = tuple(path.parts)
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise HandoffError("report handoff input is invalid")
    return parts


def _relative_parts(root: Path, target_ref: str | Path) -> tuple[str, ...]:
    try:
        candidate = Path(target_ref).expanduser()
        relative = (
            candidate.relative_to(root)
            if candidate.is_absolute()
            else candidate
        )
        return _safe_parts(relative)
    except (OSError, RuntimeError, ValueError) as error:
        raise HandoffError("report handoff input is invalid") from error


@contextmanager
def _confined_parent(
    root: Path,
    relative_parts: tuple[str, ...],
    *,
    create_directories: bool = False,
) -> Iterator[tuple[int, str]]:
    descriptors: list[int] = []
    try:
        current = os.open(root, DIRECTORY_FLAGS)
        descriptors.append(current)
        for part in relative_parts[:-1]:
            try:
                child = os.open(part, DIRECTORY_FLAGS, dir_fd=current)
            except FileNotFoundError:
                if not create_directories:
                    raise
                os.mkdir(part, 0o700, dir_fd=current)
                child = os.open(part, DIRECTORY_FLAGS, dir_fd=current)
            descriptors.append(child)
            current = child
        yield current, relative_parts[-1]
    except (OSError, ValueError) as error:
        raise HandoffError("report handoff input is invalid") from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_open_file(
    parent_fd: int,
    name: str,
    *,
    identity: Path,
    maximum: int,
    kind: str,
    open_fault_hook: OpenFaultHook | None,
) -> bytes:
    descriptor = -1
    try:
        descriptor = os.open(name, FILE_FLAGS, dir_fd=parent_fd)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size > maximum
        ):
            raise HandoffError("report handoff input is invalid")
        if open_fault_hook is not None:
            open_fault_hook(kind, str(identity))
        path_state = os.stat(
            name, dir_fd=parent_fd, follow_symlinks=False
        )
        if (
            path_state.st_dev != before.st_dev
            or path_state.st_ino != before.st_ino
        ):
            raise HandoffError("report handoff input is invalid")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(content) > maximum
            or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
        ):
            raise HandoffError("report handoff input is invalid")
        path_after = os.stat(
            name, dir_fd=parent_fd, follow_symlinks=False
        )
        if (
            path_after.st_dev != after.st_dev
            or path_after.st_ino != after.st_ino
        ):
            raise HandoffError("report handoff input is invalid")
        return content
    except (OSError, ValueError) as error:
        raise HandoffError("report handoff input is invalid") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_confined(
    root: Path,
    relative_parts: tuple[str, ...],
    maximum: int,
    *,
    kind: str,
    open_fault_hook: OpenFaultHook | None = None,
) -> VerifiedFile:
    identity = root.joinpath(*relative_parts)
    with _confined_parent(root, relative_parts) as (parent_fd, name):
        content = _read_open_file(
            parent_fd,
            name,
            identity=identity,
            maximum=maximum,
            kind=kind,
            open_fault_hook=open_fault_hook,
        )
    return VerifiedFile(identity, relative_parts, content)


def _target_payload(
    content: bytes, target_identity: Path
) -> dict[str, object]:
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HandoffError("report handoff input is invalid") from error
    if not isinstance(payload, dict) or payload.get("mode") not in MODES:
        raise HandoffError("report handoff input is invalid")
    artifacts = payload.get("artifacts")
    report = (
        artifacts.get("report")
        if isinstance(artifacts, dict)
        else None
    )
    if not isinstance(report, str) or not report:
        raise HandoffError("report handoff input is invalid")
    canonical = Path(report).expanduser()
    if not canonical.is_absolute():
        canonical = target_identity.parent / canonical
    try:
        canonical.resolve(strict=False).relative_to(
            target_identity.parent
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise HandoffError("report handoff input is invalid") from error
    return dict(payload)


def _identifiers(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise HandoffError("report handoff input is invalid")
    try:
        items = tuple(values)
    except TypeError as error:
        raise HandoffError("report handoff input is invalid") from error
    if len(items) > MAX_SNAPSHOT_IDENTIFIERS:
        raise HandoffError("report handoff input is invalid")
    for value in items:
        if (
            not isinstance(value, str)
            or not value
            or len(value) > MAX_IDENTIFIER_CHARS
            or not value.isprintable()
        ):
            raise HandoffError("report handoff input is invalid")
    return tuple(sorted(set(items)))


def _analysis_snapshot(content: bytes) -> AnalysisSnapshot:
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HandoffError("report handoff input is invalid") from error
    if not isinstance(payload, dict) or set(payload) != SNAPSHOT_KEYS:
        raise HandoffError("report handoff input is invalid")
    mode = payload.get("mode")
    deployable_ids = payload.get("deployable_subject_ids")
    relationship_ids = payload.get("relationship_edge_ids")
    if (
        mode not in MODES
        or not isinstance(deployable_ids, list)
        or not isinstance(relationship_ids, list)
    ):
        raise HandoffError("report handoff input is invalid")
    normalized_deployables = _identifiers(deployable_ids)
    normalized_relationships = _identifiers(relationship_ids)
    if (
        tuple(deployable_ids) != normalized_deployables
        or tuple(relationship_ids) != normalized_relationships
    ):
        raise HandoffError("report handoff input is invalid")
    return AnalysisSnapshot(
        mode=str(mode),
        deployable_subject_ids=normalized_deployables,
        relationship_edge_ids=normalized_relationships,
    )


def _write_all(descriptor: int, content: bytes) -> None:
    position = 0
    while position < len(content):
        position += os.write(descriptor, content[position:])


def _install_immutable(
    root: Path,
    relative_parts: tuple[str, ...],
    content: bytes,
) -> Path:
    temporary_name = f".snapshot-{secrets.token_hex(12)}.tmp"
    descriptor = -1
    try:
        with _confined_parent(
            root, relative_parts, create_directories=True
        ) as (parent_fd, name):
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent_fd,
            )
            _write_all(descriptor, content)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            try:
                os.link(
                    temporary_name,
                    name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileExistsError:
                existing = _read_open_file(
                    parent_fd,
                    name,
                    identity=root.joinpath(*relative_parts),
                    maximum=MAX_SNAPSHOT_BYTES,
                    kind="snapshot",
                    open_fault_hook=None,
                )
                if existing != content:
                    raise HandoffError(
                        "report handoff input is invalid"
                    )
            os.unlink(temporary_name, dir_fd=parent_fd)
            os.fsync(parent_fd)
    except OSError as error:
        raise HandoffError("report handoff input is invalid") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            with _confined_parent(
                root, relative_parts, create_directories=False
            ) as (parent_fd, _):
                os.unlink(temporary_name, dir_fd=parent_fd)
        except (FileNotFoundError, HandoffError):
            pass
    return root.joinpath(*relative_parts)


def _helper_target(target_ref: Path) -> tuple[Path, VerifiedFile]:
    try:
        candidate = Path(target_ref).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        root = Path(candidate.anchor or os.sep)
        target = _read_confined(
            root,
            _relative_parts(root, candidate),
            MAX_TARGET_BYTES,
            kind="target",
        )
        return root, target
    except (OSError, RuntimeError, ValueError) as error:
        raise HandoffError("report handoff input is invalid") from error


def create_start_handoff(
    target_ref: Path,
    *,
    deployable_subject_ids: Iterable[str],
    relationship_edge_ids: Iterable[str],
) -> dict[str, str]:
    root, target = _helper_target(target_ref)
    mode = str(
        _target_payload(target.content, target.identity)["mode"]
    )
    snapshot_bytes = _canonical_bytes(
        {
            "mode": mode,
            "deployable_subject_ids": _identifiers(
                deployable_subject_ids
            ),
            "relationship_edge_ids": _identifiers(
                relationship_edge_ids
            ),
        }
    )
    if len(snapshot_bytes) > MAX_SNAPSHOT_BYTES:
        raise HandoffError("report handoff input is invalid")

    target_hash = sha256(target.content).hexdigest()
    snapshot_id = sha256(snapshot_bytes).hexdigest()
    snapshot_parts = (
        *target.relative_parts[:-1],
        ".report-session",
        "snapshots",
        f"{snapshot_id}.json",
    )
    _install_immutable(root, snapshot_parts, snapshot_bytes)
    retry_hash = sha256(
        f"{target_hash}:{snapshot_id}".encode("ascii")
    ).hexdigest()
    return {
        "target_ref": str(target.identity),
        "target_sha256": target_hash,
        "analysis_snapshot_id": snapshot_id,
        "idempotency_key": f"report-start-{retry_hash}",
    }


class ReportStartResolver:
    def __init__(
        self,
        service: object,
        *,
        workspace_root: Path,
        configured_target_json: Path | None = None,
        open_fault_hook: OpenFaultHook | None = None,
    ):
        self.service = service
        try:
            self.workspace_root = Path(workspace_root).expanduser().resolve(
                strict=True
            )
            if not self.workspace_root.is_dir():
                raise HandoffError("report handoff input is invalid")
            self.configured_target_json = None
            if configured_target_json is not None:
                configured_parts = _relative_parts(
                    self.workspace_root, configured_target_json
                )
                self.configured_target_json = (
                    self.workspace_root.joinpath(*configured_parts)
                )
        except (OSError, RuntimeError, ValueError) as error:
            raise HandoffError("report handoff input is invalid") from error
        self.open_fault_hook = open_fault_hook
        self.service.lifecycle_resolver = self.lifecycle_for

    def _target(self, target_ref: str) -> VerifiedFile:
        target = _read_confined(
            self.workspace_root,
            _relative_parts(self.workspace_root, target_ref),
            MAX_TARGET_BYTES,
            kind="target",
            open_fault_hook=self.open_fault_hook,
        )
        if (
            self.configured_target_json is not None
            and target.identity != self.configured_target_json
        ):
            raise HandoffError("report handoff input is invalid")
        return target

    def _snapshot(
        self, target: VerifiedFile, analysis_snapshot_id: str
    ) -> AnalysisSnapshot:
        if SHA256.fullmatch(analysis_snapshot_id) is None:
            raise HandoffError("report handoff input is invalid")
        snapshot_parts = (
            *target.relative_parts[:-1],
            ".report-session",
            "snapshots",
            f"{analysis_snapshot_id}.json",
        )
        snapshot_file = _read_confined(
            self.workspace_root,
            snapshot_parts,
            MAX_SNAPSHOT_BYTES,
            kind="snapshot",
            open_fault_hook=self.open_fault_hook,
        )
        snapshot_bytes = snapshot_file.content
        if sha256(snapshot_bytes).hexdigest() != analysis_snapshot_id:
            raise HandoffError("report handoff input is invalid")
        return _analysis_snapshot(snapshot_bytes)

    def lifecycle_for(self, session_id: str) -> ReportLifecycle:
        snapshot = self.service.store.load(session_id)
        target_ref = (
            snapshot.target_identity
            or (
                str(self.configured_target_json)
                if self.configured_target_json is not None
                else ""
            )
        )
        target = self._target(target_ref)
        target_bytes = target.content
        if sha256(target_bytes).hexdigest() != snapshot.target_hash:
            raise HandoffError("report handoff input is invalid")
        target_payload = _target_payload(
            target_bytes, target.identity
        )
        return ReportLifecycle(
            store=self.service.store,
            target_json=target.identity,
            document_loader=self.service.load_document,
            contract=self.service.contract,
            target_payload=target_payload,
            verified_target_bytes=target_bytes,
            recovery_session_id=session_id,
        )

    def __call__(self, command: object) -> StartCommand:
        try:
            if not all(
                isinstance(getattr(command, field, None), str)
                for field in (
                    "target_ref",
                    "target_sha256",
                    "analysis_snapshot_id",
                    "idempotency_key",
                )
            ):
                raise HandoffError("report handoff input is invalid")
            target_hash = command.target_sha256
            if SHA256.fullmatch(target_hash) is None:
                raise HandoffError("report handoff input is invalid")
            target = self._target(command.target_ref)
            target_bytes = target.content
            if sha256(target_bytes).hexdigest() != target_hash:
                raise HandoffError("report handoff input is invalid")
            mode = str(
                _target_payload(
                    target_bytes, target.identity
                )["mode"]
            )
            snapshot = self._snapshot(
                target, command.analysis_snapshot_id
            )
            if snapshot.mode != mode:
                raise HandoffError("report handoff input is invalid")
            session_binding = (
                f"{command.idempotency_key}:{target_hash}:"
                f"{command.analysis_snapshot_id}:{target.identity}"
            ).encode("utf-8")
            start_command = StartCommand(
                session_id=(
                    "session-"
                    + sha256(session_binding).hexdigest()[:32]
                ),
                idempotency_key=command.idempotency_key,
                analysis_snapshot_id=command.analysis_snapshot_id,
                target_hash=target_hash,
                mode=mode,
                analysis_snapshot=snapshot,
                initial_payload={
                    "mode": mode,
                    "subjects": [],
                    "claims": [],
                    "relationships": [],
                },
                target_identity=str(target.identity),
            )
        except Exception as error:
            raise HandoffError("report handoff input is invalid") from error
        return start_command


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(
        description=(
            "Create a bounded immutable analysis snapshot and its report "
            "session handoff."
        )
    )
    argument_parser.add_argument(
        "--target-ref", required=True, type=Path
    )
    argument_parser.add_argument(
        "--deployable-subject-id", action="append", default=[]
    )
    argument_parser.add_argument(
        "--relationship-edge-id", action="append", default=[]
    )
    return argument_parser


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        handoff = create_start_handoff(
            args.target_ref,
            deployable_subject_ids=args.deployable_subject_id,
            relationship_edge_ids=args.relationship_edge_id,
        )
    except HandoffError:
        print("error: report handoff input is invalid", file=sys.stderr)
        return 1
    print(
        json.dumps(
            handoff,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
