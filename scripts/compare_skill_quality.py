#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import normalize_report
import validate_regression
import validate_report


SCORE_KEYS = [
    "deployable_component_precision",
    "deployable_component_recall",
    "excluded_item_correctness",
    "runtime_dependency_precision",
    "runtime_dependency_recall",
    "production_startup_command_correctness",
    "listener_port_correctness",
    "unsupported_claim_score",
    "valid_citation_location_rate",
    "design_input_verdict_correctness",
]


def classify_quality_delta(delta: float, threshold: float) -> str:
    if delta >= threshold:
        return "improvement"
    if delta <= -threshold:
        return "regression"
    return "no_measurable_improvement"


def score_run(normalized: dict[str, Any], expected: dict[str, Any], report_text: str, repo_root: Path) -> dict[str, Any]:
    component_precision, component_recall = _precision_recall(
        normalized.get("workload_candidates", []),
        expected.get("workload_candidates", []),
    )
    runtime_precision, runtime_recall = _precision_recall(
        _runtime_dependencies(normalized),
        _runtime_dependencies(expected),
    )
    citation_measurements = _citation_measurements(report_text, repo_root)
    unsupported_count = citation_measurements["unsupported_claim_count"]

    scores = {
        "deployable_component_precision": component_precision,
        "deployable_component_recall": component_recall,
        "excluded_item_correctness": _set_exact_score(
            normalized.get("excluded_candidates", []),
            expected.get("excluded_candidates", []),
        ),
        "runtime_dependency_precision": runtime_precision,
        "runtime_dependency_recall": runtime_recall,
        "production_startup_command_correctness": _mapping_exact_score(
            normalized.get("production_startup_commands", {}),
            expected.get("production_startup_commands", {}),
        ),
        "listener_port_correctness": _mapping_list_exact_score(
            normalized.get("listener_ports", {}),
            expected.get("listener_ports", {}),
        ),
        "unsupported_claim_score": round(1.0 / (1 + unsupported_count), 4),
        "valid_citation_location_rate": citation_measurements["valid_citation_location_rate"],
        "design_input_verdict_correctness": 1.0
        if normalized.get("design_input_verdict") == expected.get("design_input_verdict")
        else 0.0,
    }
    return {
        "scores": scores,
        "measurements": citation_measurements,
        "aggregate_score": _aggregate_score(scores),
    }


def build_comparison(
    *,
    expected_payload: dict[str, Any],
    skill_on_text: str,
    skill_off_text: str,
    repo_root: Path,
    model: str,
    runtime: str,
    prompt: str,
    repository_revision: str,
    runtime_options: Any,
    tool_permissions: str,
    threshold: float | None,
) -> dict[str, Any]:
    expected = expected_payload["expected"]
    threshold_value = threshold if threshold is not None else float(expected_payload.get("case", {}).get("value_threshold", 0.05))
    normalized_on = normalize_report.normalize_markdown(skill_on_text)
    normalized_off = normalize_report.normalize_markdown(skill_off_text)
    on_scored = score_run(normalized_on, expected, skill_on_text, repo_root)
    off_scored = score_run(normalized_off, expected, skill_off_text, repo_root)
    score_deltas = {
        key: round(on_scored["scores"][key] - off_scored["scores"][key], 4)
        for key in SCORE_KEYS
    }
    measurement_deltas = {
        "unsupported_claim_count": on_scored["measurements"]["unsupported_claim_count"]
        - off_scored["measurements"]["unsupported_claim_count"],
        "valid_citation_locations": on_scored["measurements"]["valid_citation_locations"]
        - off_scored["measurements"]["valid_citation_locations"],
        "citation_locations": on_scored["measurements"]["citation_locations"]
        - off_scored["measurements"]["citation_locations"],
    }
    aggregate_delta = round(on_scored["aggregate_score"] - off_scored["aggregate_score"], 4)
    context = {
        "model": model,
        "runtime": runtime,
        "prompt": prompt,
        "repository_revision": repository_revision,
        "runtime_options": runtime_options,
        "tool_permissions": tool_permissions,
    }
    return {
        "schema_version": 1,
        "case": expected_payload.get("case", {}),
        "threshold": threshold_value,
        "outcome": classify_quality_delta(aggregate_delta, threshold_value),
        "shared_run_context": context,
        "aggregate": {
            "skill_on": on_scored["aggregate_score"],
            "skill_off": off_scored["aggregate_score"],
            "delta": aggregate_delta,
        },
        "score_deltas": score_deltas,
        "measurement_deltas": measurement_deltas,
        "runs": {
            "skill_on": _run_payload(
                "skill-on",
                context,
                normalized_on,
                on_scored,
                _report_validation(skill_on_text, repo_root, expected_payload),
            ),
            "skill_off": _run_payload(
                "skill-off",
                context,
                normalized_off,
                off_scored,
                _report_validation(skill_off_text, repo_root, expected_payload),
            ),
        },
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Skill ON/OFF Quality Comparison",
        "",
        f"- Outcome: {payload['outcome']}",
        f"- Threshold: {payload['threshold']}",
        f"- Aggregate score delta: {payload['aggregate']['delta']:+.4f}",
        "",
        "## Runtime/model metadata",
    ]
    context = payload["shared_run_context"]
    for key in ["model", "runtime", "prompt", "repository_revision", "runtime_options", "tool_permissions"]:
        value = context[key]
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        lines.append(f"- {key}: {value}")

    lines.extend(
        [
            "",
            "## Scores",
            "| Metric | Skill ON | Skill OFF | Delta |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for key in SCORE_KEYS:
        on = payload["runs"]["skill_on"]["scores"][key]
        off = payload["runs"]["skill_off"]["scores"][key]
        delta = payload["score_deltas"][key]
        lines.append(f"| {key} | {on:.4f} | {off:.4f} | {delta:+.4f} |")

    lines.extend(
        [
            "",
            "## Diagnostics",
            f"- Skill ON unsupported claim count: {payload['runs']['skill_on']['measurements']['unsupported_claim_count']}",
            f"- Skill OFF unsupported claim count: {payload['runs']['skill_off']['measurements']['unsupported_claim_count']}",
            "- Raw normalized outputs are retained in the JSON report under `runs.*.normalized_actual`.",
            "",
        ]
    )
    return "\n".join(lines)


def _run_payload(
    skill_mode: str,
    context: dict[str, Any],
    normalized: dict[str, Any],
    scored: dict[str, Any],
    report_validation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "metadata": {
            "skill_mode": skill_mode,
            **context,
        },
        "scores": scored["scores"],
        "measurements": scored["measurements"],
        "aggregate_score": scored["aggregate_score"],
        "report_validation": report_validation,
        "normalized_actual": normalized,
    }


def _report_validation(text: str, repo_root: Path, expected_payload: dict[str, Any]) -> dict[str, Any]:
    mode = expected_payload.get("case", {}).get("report_mode", "summary")
    temp = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False)
    temp_report = Path(temp.name)
    try:
        with temp:
            temp.write(text)
        completed = validate_regression.validate_report(temp_report, repo_root, mode)
        errors = []
        if completed.returncode != 0:
            errors.append(completed.stdout + completed.stderr)
        return {"passed": completed.returncode == 0, "errors": errors}
    finally:
        try:
            temp_report.unlink()
        except FileNotFoundError:
            pass


def _runtime_dependencies(payload: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ["repository_defined_runtime_dependencies", "external_runtime_dependencies"]:
        for value in payload.get(key, []):
            if value not in values:
                values.append(value)
    return values


def _precision_recall(actual: list[str], expected: list[str]) -> tuple[float, float]:
    actual_set = set(actual)
    expected_set = set(expected)
    true_positive = len(actual_set & expected_set)
    precision = true_positive / len(actual_set) if actual_set else (1.0 if not expected_set else 0.0)
    recall = true_positive / len(expected_set) if expected_set else 1.0
    return round(precision, 4), round(recall, 4)


def _set_exact_score(actual: list[str], expected: list[str]) -> float:
    return 1.0 if set(actual) == set(expected) else 0.0


def _mapping_exact_score(actual: dict[str, str], expected: dict[str, str]) -> float:
    if not expected:
        return 1.0 if not actual else 0.0
    matches = sum(1 for key, value in expected.items() if actual.get(key) == value)
    return round(matches / len(expected), 4)


def _mapping_list_exact_score(actual: dict[str, list[str]], expected: dict[str, list[str]]) -> float:
    if not expected:
        return 1.0 if not actual else 0.0
    matches = 0
    for key, values in expected.items():
        if set(actual.get(key, [])) == set(values):
            matches += 1
    return round(matches / len(expected), 4)


def _citation_measurements(text: str, repo_root: Path) -> dict[str, Any]:
    evidence_values = [line.split("근거:", 1)[1].strip() for line in text.splitlines() if "근거:" in line]
    valid = sum(1 for evidence in evidence_values if _valid_evidence_location(evidence, repo_root))
    total = len(evidence_values)
    rate = round(valid / total, 4) if total else 0.0
    return {
        "citation_locations": total,
        "valid_citation_locations": valid,
        "valid_citation_location_rate": rate,
        "unsupported_claim_count": total - valid,
    }


def _valid_evidence_location(evidence: str, repo_root: Path) -> bool:
    if not validate_report.has_valid_evidence(evidence):
        return False
    probe = f"- 검사: 값 — 상태: 확인됨 / 근거: {evidence}"
    return not validate_report.repository_reference_errors(probe, repo_root)


def _aggregate_score(scores: dict[str, float]) -> float:
    return round(sum(scores[key] for key in SCORE_KEYS) / len(SCORE_KEYS), 4)


def _load_expected(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("quality expected fixture schema_version must be 1")
    if not isinstance(payload.get("expected"), dict):
        raise ValueError("quality expected fixture must contain expected facts")
    reconciliation = " ".join(payload.get("case", {}).get("reconciles_closed_dependencies", []))
    reconciliation += " " + payload.get("case", {}).get("reconciliation", "")
    for issue in ["#22", "#23"]:
        if issue not in reconciliation:
            raise ValueError(f"closed/not-planned dependency reconciliation is missing: {issue}")
    return payload


def _parse_runtime_options(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Skill ON and Skill OFF repository analysis quality.")
    parser.add_argument("--repo", type=Path, required=True, help="Fixture repository root")
    parser.add_argument("--expected", type=Path, required=True, help="Reviewed quality expected facts JSON")
    parser.add_argument("--skill-on-report", type=Path, required=True, help="Skill ON Markdown report")
    parser.add_argument("--skill-off-report", type=Path, required=True, help="Skill OFF Markdown report")
    parser.add_argument("--output", type=Path, help="Write machine-readable JSON report")
    parser.add_argument("--markdown-output", type=Path, help="Write Markdown comparison report")
    parser.add_argument("--model", default="unavailable")
    parser.add_argument("--runtime", default="unavailable")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--repository-revision", required=True)
    parser.add_argument("--runtime-options", default="{}")
    parser.add_argument("--tool-permissions", required=True)
    parser.add_argument("--threshold", type=float)
    args = parser.parse_args()

    try:
        expected_payload = _load_expected(args.expected)
        payload = build_comparison(
            expected_payload=expected_payload,
            skill_on_text=args.skill_on_report.read_text(encoding="utf-8"),
            skill_off_text=args.skill_off_report.read_text(encoding="utf-8"),
            repo_root=args.repo,
            model=args.model,
            runtime=args.runtime,
            prompt=args.prompt,
            repository_revision=args.repository_revision,
            runtime_options=_parse_runtime_options(args.runtime_options),
            tool_permissions=args.tool_permissions,
            threshold=args.threshold,
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"실패: {error}", file=sys.stderr)
        return 1

    json_output = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(json_output, encoding="utf-8")
    else:
        print(json_output, end="")
    if args.markdown_output:
        args.markdown_output.write_text(render_markdown(payload), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
