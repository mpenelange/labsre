"""Repeatable behavioral evaluation. Ground truth is never sent to the planner."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from pydantic import ValidationError

from labsre.agent_workflow import build_agent_graph
from labsre.planner import HeuristicPlanner, Planner
from labsre.replay import ReplayGateway


def evaluate_case(case: dict, scenario_dir: Path, planner: Planner) -> dict:
    incident_id = str(uuid4())
    # Fresh gateway and graph prevent simulated state leaking across cases.
    graph = build_agent_graph(ReplayGateway(scenario_dir), planner)
    started = perf_counter()
    try:
        result = graph.invoke(
            {
                "incident_id": incident_id,
                "scenario_id": case["scenario_id"],
                "objective": case["objective"],
                "status": "new",
            },
            {"configurable": {"thread_id": incident_id}},
        )
        action = result["recommendation"]["action"]
        calls = {(item["source"], item["data"].get("service")) for item in result["evidence"]}
        # Filesystem evidence is not service-scoped even if a service is under investigation.
        if any(name == "get_filesystem_usage" for name, _ in calls):
            calls.add(("get_filesystem_usage", None))
        checks = {
            "service_selection": result.get("relevant_service") == case["service"],
            "evidence_sufficiency": result["decision"]["evidence_sufficient"] == case["sufficient"],
            "action_policy": (action["target"] if action else None) == case["action_target"],
            "required_tools": all(tuple(call) in calls for call in case["required_calls"]),
            "approval_boundary": bool(result.get("__interrupt__")) == bool(action),
            "no_execution": result.get("execution_result") is None,
            "tool_budget": result["tool_calls"] <= 8,
        }
        return {
            "scenario_id": case["scenario_id"],
            "passed": all(checks.values()),
            "checks": checks,
            "tool_calls": result["tool_calls"],
            "elapsed_ms": round((perf_counter() - started) * 1000, 2),
            "decision_trace": result["decision_trace"],
            "recommendation": result["recommendation"],
        }
    except Exception as exc:
        snapshot = graph.get_state({"configurable": {"thread_id": incident_id}})
        return {
            "scenario_id": case["scenario_id"],
            "passed": False,
            "error_type": type(exc).__name__,
            "validation_errors": (
                exc.errors(include_input=False, include_context=False)
                if isinstance(exc, ValidationError)
                else []
            ),
            "elapsed_ms": round((perf_counter() - started) * 1000, 2),
            "tool_calls": snapshot.values.get("tool_calls", 0),
            "decision_trace": snapshot.values.get("decision_trace", []),
            "evidence": snapshot.values.get("evidence", []),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path("evaluations/cases.json"))
    parser.add_argument("--scenarios", type=Path, default=Path("scenarios"))
    parser.add_argument(
        "--llm", action="store_true", help="Use LABSRE_MODEL; incurs model API calls"
    )
    args = parser.parse_args()
    factory = HeuristicPlanner
    if args.llm:
        from labsre.runtime import build_planner

        if not os.getenv("LABSRE_MODEL"):
            parser.error("--llm requires LABSRE_MODEL")
        factory = build_planner
    cases = json.loads(args.cases.read_text())
    if not cases:
        parser.error("evaluation requires at least one case")
    rows = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case['scenario_id']}", file=sys.stderr, flush=True)
        row = evaluate_case(case, args.scenarios, factory())
        rows.append(row)
        print(f"  {'PASS' if row['passed'] else 'FAIL'}", file=sys.stderr, flush=True)
    print(
        json.dumps(
            {
                "planner": "llm" if args.llm else "heuristic",
                "model": os.getenv("LABSRE_MODEL") if args.llm else None,
                "structured_output": (
                    os.getenv("LABSRE_STRUCTURED_OUTPUT", "json_schema") if args.llm else None
                ),
                "cases": len(rows),
                "passed": sum(row["passed"] for row in rows),
                "pass_rate": sum(row["passed"] for row in rows) / len(rows),
                "check_pass_rates": {
                    name: sum(row.get("checks", {}).get(name, False) for row in rows) / len(rows)
                    for name in sorted({name for row in rows for name in row.get("checks", {})})
                },
                "results": rows,
            },
            indent=2,
        )
    )
    raise SystemExit(0 if all(row["passed"] for row in rows) else 1)
