import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_model_protocol import ProtocolError, assemble_tool_stream
from report_orchestrator import ReportContext, run_report_loop
from report_session_service import ReportSessionService, StartCommand
from report_session_store import SQLiteReportSessionStore
from report_work_units import AnalysisSnapshot


TOOL = "report_session_sync"
ARGUMENTS = {
    "session_id": "session-1",
    "known_state_version": 0,
    "request_id": "request-1",
}


def event(
    *,
    name=None,
    arguments=None,
    content=None,
    finish_reason=None,
):
    delta = {}
    if content is not None:
        delta["content"] = content
    if name is not None or arguments is not None:
        function = {}
        if name is not None:
            function["name"] = name
        if arguments is not None:
            function["arguments"] = arguments
        delta["tool_calls"] = [
            {
                "index": 0,
                "id": "call-1",
                "function": function,
            }
        ]
    return {
        "choices": [
            {
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ]
    }


def complete_stream(
    *,
    name=TOOL,
    arguments=None,
    finish_reason="tool_calls",
):
    raw = json.dumps(arguments or ARGUMENTS, separators=(",", ":"))
    midpoint = len(raw) // 2
    return [
        event(name=name, arguments=raw[:midpoint]),
        event(arguments=raw[midpoint:]),
        event(finish_reason=finish_reason),
    ]


class FakeModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def chat(self, **request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            def failed_stream():
                raise response
                yield

            return failed_stream()
        return iter(response)


class FakeService:
    def __init__(self, failure_result=None):
        self.failures = []
        self.failure_result = failure_result

    def record_transport_failure(self, session_id, lease_id, code):
        self.failures.append((session_id, lease_id, code))
        return self.failure_result


class FakeHandler:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def execute_tool_call(self, call):
        self.calls.append(call)
        return self.results.pop(0)


def initial_result():
    return {
        "ok": True,
        "session_id": "session-1",
        "state": "COLLECTING",
        "state_version": 0,
        "next_action": "sync",
        "lease": {
            "lease_id": "lease-1",
            "output_token_budget": 1024,
        },
        "progress": {"completed_units": 0, "known_units": 2},
        "diagnostics": [],
        "artifact": {},
    }


def complete_result():
    result = initial_result()
    result.update(
        {
            "state": "COMPLETE",
            "state_version": 3,
            "next_action": "complete",
            "lease": None,
            "progress": {"completed_units": 2, "known_units": 2},
            "artifact": {
                "path": "report.md",
                "sha256": "a" * 64,
                "validation": "passed",
            },
        }
    )
    return result


class ReportModelProtocolTests(unittest.TestCase):
    def test_split_json_is_assembled_only_after_tool_finish(self):
        call = assemble_tool_stream(complete_stream(), TOOL)

        self.assertEqual(call.name, TOOL)
        self.assertEqual(call.arguments, ARGUMENTS)

    def test_rejects_truncated_text_mixed_wrong_and_missing_finish(self):
        cases = (
            (
                [event(name=TOOL, arguments='{"session_id":')],
                "NO_FINISH_REASON",
            ),
            (
                [
                    event(content="보고서를 직접 쓰겠습니다."),
                    *complete_stream(),
                ],
                "TEXT_WITH_TOOL_CALL",
            ),
            (
                complete_stream(name="report_session_finalize"),
                "UNEXPECTED_TOOL",
            ),
            (
                complete_stream(finish_reason="stop"),
                "INVALID_FINISH_REASON",
            ),
            (
                [
                    event(name=TOOL, arguments='{"session_id":'),
                    event(finish_reason="tool_calls"),
                ],
                "MALFORMED_TOOL_ARGUMENTS",
            ),
        )
        for stream, code in cases:
            with self.subTest(code=code):
                with self.assertRaises(ProtocolError) as raised:
                    assemble_tool_stream(stream, TOOL)
                self.assertEqual(raised.exception.code, code)


class ReportOrchestratorTests(unittest.TestCase):
    def test_invalid_streams_never_reach_handler_then_retry_completes(self):
        model = FakeModel(
            [
                [event(name=TOOL, arguments='{"session_id":')],
                complete_stream(),
            ]
        )
        service = FakeService()
        handler = FakeHandler([complete_result()])
        context = ReportContext(initial_result=initial_result())

        artifact = run_report_loop(
            model, service, context, handler=handler
        )

        self.assertEqual(len(handler.calls), 1)
        self.assertEqual(service.failures[0][2], "NO_FINISH_REASON")
        self.assertEqual(artifact["validation"], "passed")

    def test_timeout_is_transport_failure_and_retry_key_is_stable(self):
        model = FakeModel([TimeoutError("stream timed out"), complete_stream()])
        reduced = initial_result()
        reduced["lease"] = {
            **reduced["lease"],
            "output_token_budget": 512,
        }
        service = FakeService(reduced)
        handler = FakeHandler([complete_result()])
        context = ReportContext(initial_result=initial_result())

        run_report_loop(model, service, context, handler=handler)

        self.assertEqual(service.failures[0][2], "TRANSPORT_TIMEOUT")
        first_prompt = model.requests[0]["messages"][-1]["content"]
        second_prompt = model.requests[1]["messages"][-1]["content"]
        self.assertEqual(
            json.loads(first_prompt)["retry_key"],
            json.loads(second_prompt)["retry_key"],
        )
        self.assertEqual(model.requests[1]["max_tokens"], 512)

    def test_model_call_is_sequential_deterministic_and_context_is_compact(self):
        model = FakeModel([complete_stream()])
        service = FakeService()
        handler = FakeHandler([complete_result()])
        context = ReportContext(
            base_messages=(
                {"role": "system", "content": "structured records only"},
            ),
            initial_result=initial_result(),
        )

        run_report_loop(model, service, context, handler=handler)

        request = model.requests[0]
        self.assertFalse(request["parallel_tool_calls"])
        self.assertEqual(request["temperature"], 0)
        self.assertEqual(len(request["tools"]), 1)
        self.assertEqual(
            request["tool_choice"]["function"]["name"],
            "report_session_sync",
        )
        serialized = json.dumps(request["messages"], ensure_ascii=False)
        self.assertNotIn("report_markdown", serialized)
        self.assertNotIn("source_body", serialized)

    def test_three_identical_payloads_without_progress_stop_the_loop(self):
        model = FakeModel(
            [complete_stream(), complete_stream(), complete_stream()]
        )
        service = FakeService()
        handler = FakeHandler(
            [initial_result(), initial_result(), initial_result()]
        )
        context = ReportContext(initial_result=initial_result())

        with self.assertRaisesRegex(RuntimeError, "identical"):
            run_report_loop(model, service, context, handler=handler)

        self.assertEqual(len(handler.calls), 3)

    def test_max_step_guard_stops_non_completing_unique_calls(self):
        streams = [
            complete_stream(
                arguments={**ARGUMENTS, "request_id": f"request-{index}"}
            )
            for index in range(20)
        ]
        results = []
        for index in range(20):
            result = initial_result()
            result["progress"] = {
                "completed_units": index + 1,
                "known_units": 0,
            }
            results.append(result)
        model = FakeModel(streams)
        service = FakeService()
        handler = FakeHandler(results)
        context = ReportContext(initial_result=initial_result())

        with self.assertRaisesRegex(RuntimeError, "max steps: 20"):
            run_report_loop(model, service, context, handler=handler)

        self.assertEqual(len(handler.calls), 20)

    def test_transport_failure_shrinks_lease_without_state_change(self):
        with TemporaryDirectory() as temporary:
            store = SQLiteReportSessionStore(
                Path(temporary) / "session.sqlite"
            )
            service = ReportSessionService(store)
            started = service.start(
                StartCommand(
                    session_id="session-1",
                    idempotency_key="start-key",
                    analysis_snapshot_id="snapshot-1",
                    target_hash="a" * 64,
                    mode="summary",
                    analysis_snapshot=AnalysisSnapshot(
                        mode="summary",
                        deployable_subject_ids=(),
                        relationship_edge_ids=(),
                    ),
                    initial_payload={
                        "mode": "summary",
                        "subjects": [],
                        "claims": [],
                        "relationships": [],
                    },
                )
            )

            service.record_transport_failure(
                "session-1",
                started.lease.lease_id,
                "NO_FINISH_REASON",
            )
            synced = service.sync(
                type("Sync", (), {"session_id": "session-1"})()
            )

            self.assertEqual(synced.state_version, 0)
            self.assertEqual(
                synced.lease.output_token_budget,
                started.lease.output_token_budget // 2,
            )
            self.assertEqual(synced.lease.retry_count, 1)
            store.close()


if __name__ == "__main__":
    unittest.main()
