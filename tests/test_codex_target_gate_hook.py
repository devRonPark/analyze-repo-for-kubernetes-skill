import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
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

    def test_target_missing_allows_installed_skill_read_only(self):
        self.assertEqual(self.decision("target-missing-skill-read.json"), "allow")

    def test_target_with_explicit_purpose_allows_inventory(self):
        self.assertEqual(self.decision("target-with-purpose.json"), "allow")

    def test_target_without_purpose_blocks_inventory(self):
        result = self.evaluate(self.load_fixture("target-without-purpose.json"))
        output = result["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn(HOOK.PURPOSE_QUESTION, output["permissionDecisionReason"])

    def test_target_confirmation_is_allowed_before_purpose(self):
        event = self.load_fixture("target-without-purpose.json")
        event["toolInput"]["command"] = "realpath /tmp/payments"
        self.assertEqual(self.evaluate(event)["hookSpecificOutput"]["permissionDecision"], "allow")

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
        self.assertEqual(after_purpose["hookSpecificOutput"]["permissionDecision"], "allow")

    def test_supported_target_forms_are_resolved(self):
        for target in [
            "git@github.com:example/payments.git Kubernetes 설계 준비",
            "/tmp/payments.tgz Kubernetes 설계 준비",
            "현재 저장소 Kubernetes 설계 준비",
            "Use Local path: . Kubernetes 설계 준비",
        ]:
            event = self.load_fixture("target-with-purpose.json")
            event["userPrompt"] = target
            self.assertEqual(self.evaluate(event)["hookSpecificOutput"]["permissionDecision"], "allow", target)

    def test_unrelated_sessions_are_not_blocked(self):
        event = self.load_fixture("target-missing-rg.json")
        event["userPrompt"] = "List temporary files"
        event["toolInput"]["command"] = "rg --files /tmp"
        self.assertEqual(self.evaluate(event)["hookSpecificOutput"]["permissionDecision"], "allow")


if __name__ == "__main__":
    unittest.main()
