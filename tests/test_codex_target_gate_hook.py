import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = ROOT / "scripts" / "codex_target_gate_hook.py"
SPEC = importlib.util.spec_from_file_location("codex_target_gate_hook", HOOK_PATH)
assert SPEC and SPEC.loader
HOOK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HOOK)


class CodexTargetGateHookTests(unittest.TestCase):
    def load_fixture(self, name: str) -> dict:
        return json.loads((ROOT / "tests" / "fixtures" / "hooks" / name).read_text(encoding="utf-8"))

    def evaluate(self, event: dict) -> dict:
        with tempfile.TemporaryDirectory() as cache:
            previous = os.environ.get("CODEX_TARGET_GATE_CACHE_DIR")
            os.environ["CODEX_TARGET_GATE_CACHE_DIR"] = cache
            try:
                return HOOK.evaluate_event(event)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_TARGET_GATE_CACHE_DIR", None)
                else:
                    os.environ["CODEX_TARGET_GATE_CACHE_DIR"] = previous

    def decision(self, fixture: str) -> str:
        result = self.evaluate(self.load_fixture(fixture))
        return result["hookSpecificOutput"]["permissionDecision"]

    def assertAllowed(self, result: dict) -> None:
        self.assertEqual(result, {})

    def evaluate_sequence(self, *events: dict) -> list[dict]:
        with tempfile.TemporaryDirectory() as cache:
            previous = os.environ.get("CODEX_TARGET_GATE_CACHE_DIR")
            os.environ["CODEX_TARGET_GATE_CACHE_DIR"] = cache
            try:
                return [HOOK.evaluate_event(event) for event in events]
            finally:
                if previous is None:
                    os.environ.pop("CODEX_TARGET_GATE_CACHE_DIR", None)
                else:
                    os.environ["CODEX_TARGET_GATE_CACHE_DIR"] = previous

    def test_target_missing_blocks_combined_skill_read_and_discovery(self):
        result = self.evaluate(self.load_fixture("target-missing-rg.json"))
        output = result["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertIn(HOOK.TARGET_QUESTION, output["permissionDecisionReason"])

    def test_target_missing_blocks_all_discovery_tool_calls(self):
        for command in ["rg --files /tmp", "find /tmp -maxdepth 1", "git status", "ls -la /tmp"]:
            event = self.load_fixture("target-missing-rg.json")
            event["toolInput"]["command"] = command
            self.assertEqual(self.evaluate(event)["hookSpecificOutput"]["permissionDecision"], "deny", command)

        web_event = self.load_fixture("target-missing-rg.json")
        web_event["toolName"] = "web_search"
        web_event["toolInput"] = {"query": "repository layout"}
        self.assertEqual(self.evaluate(web_event)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_targetless_slash_command_blocks_discovery_until_source_method(self):
        targetless_prompt = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "two-step-target-intake",
            "prompt": "/analyze-repo-for-kubernetes",
        }
        inventory = {
            "hook_event_name": "PreToolUse",
            "session_id": "two-step-target-intake",
            "tool_name": "Bash",
            "tool_input": {"command": "rg --files ."},
        }
        result = self.evaluate_sequence(targetless_prompt, inventory)[1]
        output = result["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn(HOOK.SOURCE_METHOD_QUESTION, output["permissionDecisionReason"])

    def test_source_method_selection_blocks_discovery_until_matching_target_value(self):
        for method_reply, expected_question in [
            ("Repository URL", HOOK.REPOSITORY_URL_QUESTION),
            ("Local directory path", HOOK.LOCAL_PATH_QUESTION),
            ("Source archive", HOOK.SOURCE_ARCHIVE_QUESTION),
        ]:
            with self.subTest(method_reply=method_reply):
                session_id = f"target-method-{method_reply.lower().replace(' ', '-')}"
                targetless_prompt = {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": session_id,
                    "prompt": "/analyze-repo-for-kubernetes",
                }
                source_method = {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": session_id,
                    "prompt": method_reply,
                }
                inventory = {
                    "hook_event_name": "PreToolUse",
                    "session_id": session_id,
                    "tool_name": "Bash",
                    "tool_input": {"command": "rg --files ."},
                }
                result = self.evaluate_sequence(targetless_prompt, source_method, inventory)[2]
                output = result["hookSpecificOutput"]
                self.assertEqual(output["permissionDecision"], "deny")
                self.assertIn(expected_question, output["permissionDecisionReason"])

    def test_target_missing_allows_installed_skill_read_only(self):
        self.assertAllowed(self.evaluate(self.load_fixture("target-missing-skill-read.json")))

    def test_target_with_explicit_purpose_allows_inventory(self):
        self.assertAllowed(self.evaluate(self.load_fixture("target-with-purpose.json")))

    def test_target_without_purpose_blocks_inventory(self):
        result = self.evaluate(self.load_fixture("target-without-purpose.json"))
        output = result["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn(HOOK.PURPOSE_QUESTION, output["permissionDecisionReason"])

    def test_target_confirmation_is_allowed_before_purpose(self):
        event = self.load_fixture("target-without-purpose.json")
        event["toolInput"]["command"] = "realpath /tmp/payments"
        self.assertAllowed(self.evaluate(event))

    def test_user_prompt_seeds_state_and_purpose_reply_unblocks_inventory(self):
        target_prompt = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "two-turn-purpose",
            "prompt": "/analyze-repo-for-kubernetes /tmp/payments",
        }
        inventory = {
            "hook_event_name": "PreToolUse",
            "session_id": "two-turn-purpose",
            "tool_name": "Bash",
            "tool_input": {"command": "rg --files /tmp/payments"},
        }
        purpose_reply = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "two-turn-purpose",
            "prompt": "Kubernetes 설계 준비",
        }
        before_purpose, _, after_purpose = self.evaluate_sequence(
            target_prompt,
            inventory,
            purpose_reply,
            deepcopy(inventory),
        )[1:]
        self.assertEqual(before_purpose["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertAllowed(after_purpose)

    def test_supported_target_forms_are_resolved(self):
        for target in [
            "git@github.com:example/payments.git Kubernetes 설계 준비",
            "/tmp/payments.tgz Kubernetes 설계 준비",
            "현재 저장소 Kubernetes 설계 준비",
            "Use Local path: . Kubernetes 설계 준비",
        ]:
            event = self.load_fixture("target-with-purpose.json")
            event["userPrompt"] = target
            self.assertAllowed(self.evaluate(event))

    def test_unrelated_sessions_are_not_blocked(self):
        event = self.load_fixture("target-missing-rg.json")
        event["userPrompt"] = "List temporary files"
        event["toolInput"]["command"] = "rg --files /tmp"
        self.assertAllowed(self.evaluate(event))

    def test_allow_response_does_not_emit_unsupported_permission_decision(self):
        result = self.evaluate(self.load_fixture("target-with-purpose.json"))
        self.assertNotIn("hookSpecificOutput", result)
        self.assertNotIn("permissionDecision", json.dumps(result))

    def test_unwritable_default_cache_falls_back_to_next_candidate(self):
        event = self.load_fixture("target-missing-rg.json")
        with tempfile.TemporaryDirectory() as cache:
            blocked_cache = Path(cache) / "blocked"
            blocked_cache.write_text("not a directory", encoding="utf-8")
            fallback_cache = Path(cache) / "fallback"
            previous = os.environ.pop("CODEX_TARGET_GATE_CACHE_DIR", None)
            try:
                with mock.patch.object(
                    HOOK,
                    "_cache_dir_candidates",
                    return_value=[blocked_cache, fallback_cache],
                ):
                    result = HOOK.evaluate_event(event)
            finally:
                if previous is not None:
                    os.environ["CODEX_TARGET_GATE_CACHE_DIR"] = previous
            self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertEqual(
                json.loads((fallback_cache / "missing-rg.json").read_text(encoding="utf-8")),
                {"phase": "source_method_required"},
            )


if __name__ == "__main__":
    unittest.main()
