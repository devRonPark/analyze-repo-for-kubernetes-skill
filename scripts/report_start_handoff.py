from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Iterable, Mapping

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


def _bounded_bytes(path: Path, maximum: int) -> bytes:
    try:
        if path.stat().st_size > maximum:
            raise HandoffError("report handoff input is invalid")
        with path.open("rb") as stream:
            content = stream.read(maximum + 1)
    except (OSError, ValueError) as error:
        raise HandoffError("report handoff input is invalid") from error
    if len(content) > maximum:
        raise HandoffError("report handoff input is invalid")
    return content


def _target_mode(content: bytes) -> str:
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HandoffError("report handoff input is invalid") from error
    if not isinstance(payload, dict) or payload.get("mode") not in MODES:
        raise HandoffError("report handoff input is invalid")
    return str(payload["mode"])


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


def _install_immutable(path: Path, content: bytes) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=".snapshot.",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_path, path)
        except FileExistsError:
            if (
                path.is_symlink()
                or _bounded_bytes(path, MAX_SNAPSHOT_BYTES) != content
            ):
                raise HandoffError("report handoff input is invalid")
    except OSError as error:
        raise HandoffError("report handoff input is invalid") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def _snapshot_destination(target: Path, snapshot_id: str) -> Path:
    directory = target.parent / ".report-session/snapshots"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        resolved = directory.resolve(strict=True)
        resolved.relative_to(target.parent)
    except (OSError, RuntimeError, ValueError) as error:
        raise HandoffError("report handoff input is invalid") from error
    return resolved / f"{snapshot_id}.json"


def create_start_handoff(
    target_ref: Path,
    *,
    deployable_subject_ids: Iterable[str],
    relationship_edge_ids: Iterable[str],
) -> dict[str, str]:
    try:
        target = Path(target_ref).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise HandoffError("report handoff input is invalid") from error
    if not target.is_file():
        raise HandoffError("report handoff input is invalid")

    target_bytes = _bounded_bytes(target, MAX_TARGET_BYTES)
    mode = _target_mode(target_bytes)
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

    target_hash = sha256(target_bytes).hexdigest()
    snapshot_id = sha256(snapshot_bytes).hexdigest()
    snapshot_path = _snapshot_destination(target, snapshot_id)
    _install_immutable(snapshot_path, snapshot_bytes)
    retry_hash = sha256(
        f"{target_hash}:{snapshot_id}".encode("ascii")
    ).hexdigest()
    return {
        "target_ref": str(target),
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
    ):
        self.service = service
        try:
            self.workspace_root = Path(workspace_root).expanduser().resolve(
                strict=True
            )
            if not self.workspace_root.is_dir():
                raise HandoffError("report handoff input is invalid")
            self.configured_target_json = (
                Path(configured_target_json).expanduser().resolve(strict=True)
                if configured_target_json is not None
                else None
            )
            if self.configured_target_json is not None:
                self.configured_target_json.relative_to(self.workspace_root)
        except (OSError, RuntimeError, ValueError) as error:
            raise HandoffError("report handoff input is invalid") from error

    def _target(self, target_ref: str) -> Path:
        try:
            candidate = Path(target_ref).expanduser()
            if not candidate.is_absolute():
                candidate = self.workspace_root / candidate
            if candidate.is_symlink():
                raise HandoffError("report handoff input is invalid")
            target = candidate.resolve(strict=True)
            target.relative_to(self.workspace_root)
        except (OSError, RuntimeError, ValueError) as error:
            raise HandoffError("report handoff input is invalid") from error
        if not target.is_file() or (
            self.configured_target_json is not None
            and target != self.configured_target_json
        ):
            raise HandoffError("report handoff input is invalid")
        return target

    def _snapshot(
        self, target: Path, analysis_snapshot_id: str
    ) -> AnalysisSnapshot:
        if SHA256.fullmatch(analysis_snapshot_id) is None:
            raise HandoffError("report handoff input is invalid")
        candidate = (
            target.parent
            / ".report-session/snapshots"
            / f"{analysis_snapshot_id}.json"
        )
        try:
            if candidate.is_symlink():
                raise HandoffError("report handoff input is invalid")
            snapshot_path = candidate.resolve(strict=True)
            snapshot_path.relative_to(self.workspace_root)
        except (OSError, RuntimeError, ValueError) as error:
            raise HandoffError("report handoff input is invalid") from error
        snapshot_bytes = _bounded_bytes(
            snapshot_path, MAX_SNAPSHOT_BYTES
        )
        if sha256(snapshot_bytes).hexdigest() != analysis_snapshot_id:
            raise HandoffError("report handoff input is invalid")
        return _analysis_snapshot(snapshot_bytes)

    def _validate_retry_binding(
        self, command: object, mode: str
    ) -> None:
        existing = self.service.store.transact(
            lambda connection: connection.execute(
                "SELECT analysis_snapshot_id, target_hash, mode "
                "FROM sessions WHERE start_idempotency_key = ?",
                (command.idempotency_key,),
            ).fetchone()
        )
        if existing is not None and (
            existing["analysis_snapshot_id"]
            != command.analysis_snapshot_id
            or existing["target_hash"] != command.target_sha256
            or existing["mode"] != mode
        ):
            raise HandoffError("report handoff input is invalid")

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
            target_bytes = _bounded_bytes(target, MAX_TARGET_BYTES)
            if sha256(target_bytes).hexdigest() != target_hash:
                raise HandoffError("report handoff input is invalid")
            mode = _target_mode(target_bytes)
            snapshot = self._snapshot(
                target, command.analysis_snapshot_id
            )
            if snapshot.mode != mode:
                raise HandoffError("report handoff input is invalid")
            self._validate_retry_binding(command, mode)

            lifecycle = ReportLifecycle(
                store=self.service.store,
                target_json=target,
                document_loader=self.service.load_document,
                contract=self.service.contract,
            )
            session_binding = (
                f"{command.idempotency_key}:{target_hash}:"
                f"{command.analysis_snapshot_id}"
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
            )
        except Exception as error:
            raise HandoffError("report handoff input is invalid") from error
        self.service.lifecycle = lifecycle
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
