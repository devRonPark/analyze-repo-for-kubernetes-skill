from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Callable, Mapping

import report_contract
from report_diagnostics import Diagnostic
import report_records
import report_renderer
from report_session_models import SessionState
from report_session_service import (
    ToolResult,
    _result_from_json,
    _result_json,
)
from report_session_store import SQLiteReportSessionStore
import validate_report
from validate_target_report import load_target


TARGET_GUARD_TIMEOUT_SECONDS = 30
MAX_TARGET_GUARD_OUTPUT = 32_768


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _session_token(session_id: str) -> str:
    token = re.sub(r"[^0-9A-Za-z._-]", "-", session_id).strip(".-")
    if (
        not token
        or token in {".", ".."}
        or "report" in token.lower()
    ):
        return sha256(session_id.encode("utf-8")).hexdigest()[:20]
    return token


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_bytes(path: Path, content: bytes) -> None:
    with path.open("wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_directory(path.parent)


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / ".journal.tmp"
    _write_bytes(
        temporary,
        (_canonical_json(payload) + "\n").encode("utf-8"),
    )
    os.replace(temporary, path)
    _fsync_directory(path.parent)


class ReportLifecycle:
    def __init__(
        self,
        *,
        store: SQLiteReportSessionStore,
        target_json: Path,
        document_loader: Callable[
            [str], report_records.ReportDocument
        ],
        contract: report_contract.ReportContract | None = None,
        renderer: Callable[
            [report_records.ReportDocument, report_contract.ReportContract],
            str,
        ] = report_renderer.render_report,
        crash_hook: Callable[[str], None] | None = None,
    ):
        self.store = store
        self.target_json = Path(target_json)
        self.document_loader = document_loader
        self.contract = contract or report_contract.load_report_contract()
        self.renderer = renderer
        self.crash_hook = crash_hook or (lambda phase: None)
        self.target = load_target(self.target_json)
        artifacts = self.target.get("artifacts")
        if not isinstance(artifacts, dict):
            raise ValueError("target.json에 artifacts object가 없습니다")
        canonical = artifacts.get("report")
        if not isinstance(canonical, str) or not canonical:
            raise ValueError("target.json artifacts.report가 없습니다")
        self.canonical_path = Path(canonical)
        self.journal_path = (
            self.canonical_path.parent
            / ".report-session/finalize-journal.json"
        )

    def candidate_path(self, session_id: str) -> Path:
        return self.canonical_path.parent / (
            f".candidate-{_session_token(session_id)}.tmp"
        )

    def previous_path(self, session_id: str) -> Path:
        return self.canonical_path.parent / (
            f".previous-{_session_token(session_id)}.tmp"
        )

    def _coverage(self, connection, session_id: str) -> tuple[int, int]:
        return (
            connection.execute(
                "SELECT COUNT(*) FROM work_units "
                "WHERE session_id = ? AND status = 'COMPLETE'",
                (session_id,),
            ).fetchone()[0],
            connection.execute(
                "SELECT COUNT(*) FROM work_units WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0],
        )

    def _existing_result(
        self, session_id: str, idempotency_key: str
    ) -> ToolResult | None:
        row = self.store.transact(
            lambda connection: connection.execute(
                "SELECT result_json FROM finalize_results "
                "WHERE session_id = ? AND idempotency_key = ?",
                (session_id, idempotency_key),
            ).fetchone()
        )
        return _result_from_json(row["result_json"]) if row else None

    def _current_result(
        self, session_id: str, status: str, message: str
    ) -> ToolResult:
        snapshot = self.store.load(session_id)
        coverage = self.store.transact(
            lambda connection: self._coverage(connection, session_id)
        )
        return ToolResult(
            status,
            session_id,
            snapshot.state.value,
            snapshot.state_version,
            snapshot.active_lease,
            coverage,
            message,
        )

    def _transition(
        self,
        session_id: str,
        *,
        state: SessionState,
        event: str,
        details: Mapping[str, object] | None = None,
    ) -> tuple[int, tuple[int, int]]:
        def operation(connection):
            row = connection.execute(
                "SELECT state_version FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise KeyError(
                    f"report session을 찾을 수 없습니다: {session_id}"
                )
            version = row["state_version"] + 1
            connection.execute(
                "UPDATE sessions SET state = ?, state_version = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                (state.value, version, session_id),
            )
            connection.execute(
                "INSERT INTO audit_events("
                "session_id, event_type, state_version, details_json"
                ") VALUES (?, ?, ?, ?)",
                (
                    session_id,
                    event,
                    version,
                    _canonical_json(details or {}),
                ),
            )
            return version, self._coverage(connection, session_id)

        return self.store.transact(operation)

    def _begin(
        self,
        session_id: str,
        expected_state_version: int,
    ) -> ToolResult | tuple[int, tuple[int, int]]:
        def operation(connection):
            row = connection.execute(
                "SELECT state, state_version FROM sessions "
                "WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise KeyError(
                    f"report session을 찾을 수 없습니다: {session_id}"
                )
            coverage = self._coverage(connection, session_id)
            if row["state_version"] != expected_state_version:
                return ToolResult(
                    "sync_required",
                    session_id,
                    row["state"],
                    row["state_version"],
                    None,
                    coverage,
                    "expected_state_version이 stale합니다",
                )
            if row["state"] != SessionState.READY.value:
                return ToolResult(
                    "rejected",
                    session_id,
                    row["state"],
                    row["state_version"],
                    None,
                    coverage,
                    "READY session만 finalize할 수 있습니다",
                )
            version = row["state_version"] + 1
            connection.execute(
                "UPDATE sessions SET state = ?, state_version = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                (SessionState.ASSEMBLING.value, version, session_id),
            )
            connection.execute(
                "INSERT INTO audit_events("
                "session_id, event_type, state_version, details_json"
                ") VALUES (?, 'FINALIZE_STARTED', ?, '{}')",
                (session_id, version),
            )
            return version, coverage

        return self.store.transact(operation)

    def _journal(
        self,
        journal: dict[str, object],
        phase: str,
        **updates: object,
    ) -> dict[str, object]:
        updated = {**journal, **updates, "phase": phase}
        _atomic_json(self.journal_path, updated)
        return updated

    def _load_journal(self) -> dict[str, object] | None:
        if not self.journal_path.is_file():
            return None
        payload = json.loads(self.journal_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("finalize journal root는 object여야 합니다")
        return payload

    def finish_repair_routing(self, session_id: str) -> None:
        journal = self._load_journal()
        if journal is None:
            return
        if (
            journal.get("session_id") != session_id
            or journal.get("phase") != "validation_failed"
        ):
            raise RuntimeError(
                "현재 session의 validation failure journal이 아닙니다"
            )
        Path(str(journal["candidate_path"])).unlink(missing_ok=True)
        Path(str(journal["previous_path"])).unlink(missing_ok=True)
        self.journal_path.unlink(missing_ok=True)
        _fsync_directory(self.canonical_path.parent)

    def _candidate_diagnostics(
        self, candidate: Path, mode: str
    ) -> tuple[Diagnostic, ...]:
        repository_root = self.target.get("analysis_root")
        return validate_report.validate_text(
            candidate.read_text(encoding="utf-8"),
            mode=mode,
            contract="new",
            repository_root=(
                Path(repository_root)
                if isinstance(repository_root, str)
                else None
            ),
        )

    def _run_target_guard(self) -> bool:
        validation = self.target.get("validation")
        command = (
            validation.get("command")
            if isinstance(validation, dict)
            else None
        )
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(item, str) and item for item in command)
        ):
            raise RuntimeError(
                "target.json validation.command가 유효하지 않습니다"
            )
        target_path = self.target_json.expanduser().resolve(strict=False)
        command_paths = {
            Path(item).expanduser().resolve(strict=False)
            for item in command
        }
        if target_path not in command_paths:
            raise RuntimeError(
                "target.json validation.command가 canonical target guard를 "
                "호출하지 않습니다"
            )
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
                shell=False,
                timeout=TARGET_GUARD_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError(
                f"target guard infrastructure failure: {type(error).__name__}"
            ) from error
        if (
            len(completed.stdout) > MAX_TARGET_GUARD_OUTPUT
            or len(completed.stderr) > MAX_TARGET_GUARD_OUTPUT
        ):
            raise RuntimeError("target guard output limit을 초과했습니다")
        return completed.returncode == 0

    def _rollback(self, previous: Path) -> None:
        if previous.exists() or previous.is_symlink():
            if self.canonical_path.exists() or self.canonical_path.is_symlink():
                self.canonical_path.unlink()
            os.replace(previous, self.canonical_path)
            _fsync_directory(self.canonical_path.parent)
        elif self.canonical_path.exists() or self.canonical_path.is_symlink():
            self.canonical_path.unlink()
            _fsync_directory(self.canonical_path.parent)

    def _terminal_failure(
        self,
        journal: dict[str, object],
        message: str,
    ) -> ToolResult:
        session_id = str(journal["session_id"])
        candidate = Path(str(journal["candidate_path"]))
        previous = Path(str(journal["previous_path"]))
        self._rollback(previous)
        candidate.unlink(missing_ok=True)
        version, coverage = self._transition(
            session_id,
            state=SessionState.FAILED,
            event="FINALIZE_FAILED",
            details={"message": message},
        )
        self.journal_path.unlink(missing_ok=True)
        return ToolResult(
            "failed",
            session_id,
            SessionState.FAILED.value,
            version,
            None,
            coverage,
            message,
        )

    def _complete(
        self, journal: dict[str, object]
    ) -> ToolResult:
        session_id = str(journal["session_id"])
        idempotency_key = str(journal["idempotency_key"])
        content = self.canonical_path.read_bytes()
        artifact = {
            "path": str(self.canonical_path),
            "sha256": sha256(content).hexdigest(),
            "byte_size": len(content),
            "validation": "passed",
        }

        def operation(connection):
            existing = connection.execute(
                "SELECT result_json FROM finalize_results "
                "WHERE session_id = ? AND idempotency_key = ?",
                (session_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                return _result_from_json(existing["result_json"])
            row = connection.execute(
                "SELECT state_version FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            version = row["state_version"] + 1
            coverage = self._coverage(connection, session_id)
            result = ToolResult(
                "complete",
                session_id,
                SessionState.COMPLETE.value,
                version,
                None,
                coverage,
                "",
                artifact,
            )
            connection.execute(
                "UPDATE sessions SET state = ?, state_version = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                (SessionState.COMPLETE.value, version, session_id),
            )
            connection.execute(
                "INSERT INTO finalize_results("
                "session_id, idempotency_key, result_json"
                ") VALUES (?, ?, ?)",
                (session_id, idempotency_key, _result_json(result)),
            )
            connection.execute(
                "INSERT INTO audit_events("
                "session_id, event_type, state_version, details_json"
                ") VALUES (?, 'FINALIZE_COMPLETED', ?, ?)",
                (session_id, version, _canonical_json(artifact)),
            )
            return result

        return self.store.transact(operation)

    def _resume(
        self, journal: dict[str, object]
    ) -> ToolResult:
        session_id = str(journal["session_id"])
        candidate = Path(str(journal["candidate_path"]))
        previous = Path(str(journal["previous_path"]))
        phase = str(journal["phase"])

        if phase == "candidate_write_pending":
            document = self.document_loader(session_id)
            rendered = self.renderer(document, self.contract)
            _write_bytes(candidate, rendered.encode("utf-8"))
            journal = self._journal(journal, "candidate_written")
            self.crash_hook("candidate_written")
            phase = "candidate_written"

        if phase == "candidate_written":
            snapshot = self.store.load(session_id)
            if snapshot.state is SessionState.ASSEMBLING:
                self._transition(
                    session_id,
                    state=SessionState.VALIDATING,
                    event="CANDIDATE_RENDERED",
                )
            diagnostics = self._candidate_diagnostics(
                candidate, str(journal["mode"])
            )
            if diagnostics:
                journal = self._journal(
                    journal,
                    "validation_failed",
                    diagnostics=[
                        diagnostic.to_dict()
                        for diagnostic in diagnostics
                    ],
                )
                candidate.unlink(missing_ok=True)
                version, coverage = self._transition(
                    session_id,
                    state=SessionState.REPAIRING,
                    event="CANDIDATE_REJECTED",
                    details={
                        "diagnostics": journal["diagnostics"],
                    },
                )
                return ToolResult(
                    "validation_failed",
                    session_id,
                    SessionState.REPAIRING.value,
                    version,
                    None,
                    coverage,
                    _canonical_json(journal["diagnostics"]),
                )
            journal = self._journal(journal, "swap_pending")
            phase = "swap_pending"

        if phase == "swap_pending":
            if (
                self.canonical_path.exists()
                or self.canonical_path.is_symlink()
            ) and not (previous.exists() or previous.is_symlink()):
                os.replace(self.canonical_path, previous)
                _fsync_directory(self.canonical_path.parent)
            journal = self._journal(journal, "backup_ready")
            phase = "backup_ready"

        if phase == "backup_ready":
            if candidate.exists():
                os.replace(candidate, self.canonical_path)
                _fsync_directory(self.canonical_path.parent)
            elif not self.canonical_path.exists():
                return self._terminal_failure(
                    journal, "candidate artifact가 없습니다"
                )
            journal = self._journal(
                journal, "target_validation_pending"
            )
            phase = "target_validation_pending"

        if phase == "target_validation_pending":
            try:
                valid = self._run_target_guard()
            except RuntimeError as error:
                return self._terminal_failure(journal, str(error))
            if not valid:
                return self._terminal_failure(
                    journal, "target guard validation failed"
                )
            result = self._complete(journal)
            previous.unlink(missing_ok=True)
            candidate.unlink(missing_ok=True)
            self.journal_path.unlink(missing_ok=True)
            _fsync_directory(self.canonical_path.parent)
            return result

        if phase == "validation_failed":
            return self._current_result(
                session_id,
                "validation_failed",
                _canonical_json(journal.get("diagnostics", [])),
            )
        raise RuntimeError(f"지원하지 않는 finalize journal phase: {phase}")

    def _cleanup_completed_journal(
        self,
        session_id: str,
        idempotency_key: str,
    ) -> None:
        journal = self._load_journal()
        if (
            journal is None
            or journal.get("session_id") != session_id
            or journal.get("idempotency_key") != idempotency_key
        ):
            return
        Path(str(journal["candidate_path"])).unlink(missing_ok=True)
        Path(str(journal["previous_path"])).unlink(missing_ok=True)
        self.journal_path.unlink(missing_ok=True)

    def finalize(
        self,
        session_id: str,
        expected_state_version: int,
        idempotency_key: str,
    ) -> ToolResult:
        existing = self._existing_result(session_id, idempotency_key)
        if existing is not None:
            self._cleanup_completed_journal(
                session_id, idempotency_key
            )
            return existing

        journal = self._load_journal()
        if journal is not None:
            if (
                journal.get("session_id") != session_id
                or journal.get("idempotency_key") != idempotency_key
                or journal.get("expected_state_version")
                != expected_state_version
            ):
                return self._current_result(
                    session_id,
                    "rejected",
                    "다른 finalize operation이 복구 대기 중입니다",
                )
            return self._resume(journal)

        begun = self._begin(session_id, expected_state_version)
        if isinstance(begun, ToolResult):
            return begun
        state_version, _ = begun
        candidate = self.candidate_path(session_id)
        previous = self.previous_path(session_id)
        journal = self._journal(
            {
                "session_id": session_id,
                "expected_state_version": expected_state_version,
                "idempotency_key": idempotency_key,
                "candidate_path": str(candidate),
                "previous_path": str(previous),
                "canonical_path": str(self.canonical_path),
                "mode": self.store.load(session_id).mode,
                "assembling_state_version": state_version,
            },
            "candidate_write_pending",
        )
        return self._resume(journal)
