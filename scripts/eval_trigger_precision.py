#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any


SKILL_NAME = "analyze-repo-for-kubernetes"


@dataclass(frozen=True)
class TriggerCase:
    id: str
    prompt: str
    should_trigger: bool
    rationale: str
    runtime_events: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class TriggerResult:
    id: str
    prompt: str
    should_trigger: bool
    observed_trigger: bool
    rationale: str


@dataclass(frozen=True)
class TriggerMetrics:
    total: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    precision: float
    recall: float


@dataclass(frozen=True)
class TriggerReport:
    metrics: TriggerMetrics
    results: tuple[TriggerResult, ...]


def load_cases(path: Path) -> tuple[TriggerCase, ...]:
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_cases, list):
        raise ValueError("trigger cases must be a JSON list")

    cases: list[TriggerCase] = []
    for index, raw_case in enumerate(raw_cases):
        if not isinstance(raw_case, dict):
            raise ValueError(f"trigger case at index {index} must be an object")
        case_id = _required_string(raw_case, "id", index)
        prompt = _required_string(raw_case, "prompt", index)
        should_trigger = raw_case.get("should_trigger")
        if not isinstance(should_trigger, bool):
            raise ValueError(f"trigger case {case_id} must define boolean should_trigger")
        rationale = raw_case.get("rationale", "")
        if not isinstance(rationale, str):
            raise ValueError(f"trigger case {case_id} rationale must be a string")
        runtime_events = raw_case.get("runtime_events", [])
        if not isinstance(runtime_events, list) or not all(isinstance(event, dict) for event in runtime_events):
            raise ValueError(f"trigger case {case_id} runtime_events must be a list of objects")
        cases.append(
            TriggerCase(
                id=case_id,
                prompt=prompt,
                should_trigger=should_trigger,
                rationale=rationale,
                runtime_events=tuple(runtime_events),
            )
        )
    return tuple(cases)


def apply_runtime_event_overrides(cases: tuple[TriggerCase, ...], path: Path) -> tuple[TriggerCase, ...]:
    raw_events = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_events, dict):
        raise ValueError("runtime event overrides must be a JSON object keyed by case id")

    overrides: dict[str, tuple[dict[str, Any], ...]] = {}
    for case_id, events in raw_events.items():
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("runtime event override keys must be non-empty case ids")
        if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
            raise ValueError(f"runtime event override for {case_id} must be a list of objects")
        overrides[case_id] = tuple(events)

    case_ids = {case.id for case in cases}
    unknown_ids = sorted(set(overrides) - case_ids)
    if unknown_ids:
        raise ValueError(f"runtime event overrides reference unknown case ids: {', '.join(unknown_ids)}")

    return tuple(
        TriggerCase(
            id=case.id,
            prompt=case.prompt,
            should_trigger=case.should_trigger,
            rationale=case.rationale,
            runtime_events=overrides.get(case.id, case.runtime_events),
        )
        for case in cases
    )


def evaluate_cases(cases: tuple[TriggerCase, ...]) -> TriggerReport:
    results = tuple(
        TriggerResult(
            id=case.id,
            prompt=case.prompt,
            should_trigger=case.should_trigger,
            observed_trigger=_skill_was_invoked(case.runtime_events),
            rationale=case.rationale,
        )
        for case in cases
    )

    true_positives = sum(1 for result in results if result.should_trigger and result.observed_trigger)
    false_positives = sum(1 for result in results if not result.should_trigger and result.observed_trigger)
    true_negatives = sum(1 for result in results if not result.should_trigger and not result.observed_trigger)
    false_negatives = sum(1 for result in results if result.should_trigger and not result.observed_trigger)
    precision = true_positives / (true_positives + false_positives) if true_positives + false_positives else 0.0
    recall = true_positives / (true_positives + false_negatives) if true_positives + false_negatives else 0.0

    return TriggerReport(
        metrics=TriggerMetrics(
            total=len(results),
            true_positives=true_positives,
            false_positives=false_positives,
            true_negatives=true_negatives,
            false_negatives=false_negatives,
            precision=precision,
            recall=recall,
        ),
        results=results,
    )


def report_to_dict(report: TriggerReport) -> dict[str, Any]:
    return {
        "metrics": {
            "total": report.metrics.total,
            "true_positives": report.metrics.true_positives,
            "false_positives": report.metrics.false_positives,
            "true_negatives": report.metrics.true_negatives,
            "false_negatives": report.metrics.false_negatives,
            "precision": report.metrics.precision,
            "recall": report.metrics.recall,
        },
        "results": [
            {
                "id": result.id,
                "prompt": result.prompt,
                "should_trigger": result.should_trigger,
                "observed_trigger": result.observed_trigger,
                "outcome": "pass" if result.should_trigger == result.observed_trigger else "fail",
                "rationale": result.rationale,
            }
            for result in report.results
        ],
    }


def render_markdown(report: TriggerReport) -> str:
    lines = [
        "# Trigger Precision Report",
        "",
        f"- Total cases: {report.metrics.total}",
        f"- True positives: {report.metrics.true_positives}",
        f"- False positives: {report.metrics.false_positives}",
        f"- True negatives: {report.metrics.true_negatives}",
        f"- False negatives: {report.metrics.false_negatives}",
        f"- Precision: {report.metrics.precision:.3f}",
        f"- Recall: {report.metrics.recall:.3f}",
        "",
        "| id | should trigger | observed trigger | outcome |",
        "| --- | --- | --- | --- |",
    ]
    for result in report.results:
        outcome = "pass" if result.should_trigger == result.observed_trigger else "fail"
        lines.append(
            f"| {result.id} | {_bool_text(result.should_trigger)} | "
            f"{_bool_text(result.observed_trigger)} | {outcome} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate analyze-repo-for-kubernetes trigger precision cases.")
    parser.add_argument("cases", type=Path, help="JSON trigger case fixture")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown", help="Report format")
    parser.add_argument("--output", type=Path, help="Write report to this path instead of stdout")
    parser.add_argument(
        "--runtime-events",
        type=Path,
        help="JSON object keyed by case id with live runtime events captured outside CI",
    )
    parser.add_argument(
        "--allow-live-runtime",
        action="store_true",
        help="Allow externally captured live runtime events to override fixture events",
    )
    args = parser.parse_args(argv)

    if args.runtime_events and not args.allow_live_runtime:
        parser.error("--runtime-events requires --allow-live-runtime")

    cases = load_cases(args.cases)
    if args.runtime_events:
        cases = apply_runtime_event_overrides(cases, args.runtime_events)
    report = evaluate_cases(cases)
    if args.format == "json":
        output = json.dumps(report_to_dict(report), ensure_ascii=False, indent=2) + "\n"
    else:
        output = render_markdown(report)

    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


def _required_string(raw_case: dict[str, Any], key: str, index: int) -> str:
    value = raw_case.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"trigger case at index {index} must define non-empty {key}")
    return value


def _skill_was_invoked(events: tuple[dict[str, Any], ...]) -> bool:
    for event in events:
        if event.get("skill") == SKILL_NAME or event.get("skill_name") == SKILL_NAME:
            return True
        if event.get("name") == SKILL_NAME and event.get("event") in {"skill_invocation", "skill_used"}:
            return True
    return False


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


if __name__ == "__main__":
    sys.exit(main())
