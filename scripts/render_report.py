#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

import report_contract
import report_records
import report_renderer


def _atomic_write(output: Path, text: str) -> None:
    if output.is_symlink():
        raise ValueError(f"output symlink는 허용되지 않습니다: {output}")
    if not output.parent.is_dir():
        raise ValueError(f"output directory를 찾을 수 없습니다: {output.parent}")

    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if output.is_symlink():
            raise ValueError(f"output symlink는 허용되지 않습니다: {output}")
        os.replace(temporary, output)
        directory_descriptor = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="typed semantic records를 결정론적 Markdown 보고서로 렌더링합니다."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--repo-root",
        type=Path,
        required=True,
        help="repository-relative evidence를 검증할 분석 대상 root",
    )
    args = parser.parse_args(argv)

    try:
        document = report_records.load_report_document(args.input)
        contract = report_contract.load_report_contract()
        diagnostics = report_records.validate_document(
            document,
            contract,
            repository_root=args.repo_root,
        )
        if diagnostics:
            details = "; ".join(
                f"{diagnostic.code}: {diagnostic.message}"
                for diagnostic in diagnostics
            )
            raise ValueError(details)
        rendered = report_renderer.render_report(document, contract)
        _atomic_write(args.output, rendered)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"실패: {error}", file=sys.stderr)
        return 1

    print(f"성공: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
