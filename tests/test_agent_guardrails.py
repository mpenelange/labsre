from pathlib import Path

import pytest
from langgraph.types import Command

from labsre.agent_workflow import build_agent_graph
from labsre.planner import ScriptedPlanner
from labsre.replay import ReplayGateway

SCENARIOS = Path(__file__).parents[1] / "scenarios"


def decision(arguments=None, **changes):
    return {
        "situation_summary": "Inspect the service.",
        "evidence_sufficient": False,
        "relevant_service": "paperless_web",
        "confidence": 0.9,
        "reasoning_summary": "Confirm runtime state.",
        "next_tool": {
            "name": "get_recent_events",
            "purpose": "Inspect recent lifecycle.",
            "arguments": arguments or {},
        },
        **changes,
    }


def run(decisions):
    graph = build_agent_graph(ReplayGateway(SCENARIOS), ScriptedPlanner(decisions))
    config = {"configurable": {"thread_id": "guardrail"}}
    result = graph.invoke(
        {
            "incident_id": "guardrail",
            "scenario_id": "service-stopped",
            "objective": "Inspect paperless_web",
        },
        config,
    )
    return graph, config, result


def test_default_arguments_cannot_bypass_duplicate_detection():
    with pytest.raises(ValueError, match="identical tool request"):
        run([decision(), decision({"service": "paperless_web", "limit": 50})])


@pytest.mark.parametrize(
    "arguments",
    [
        {"limit": True},
        {"limit": "50"},
        {"limit": 101},
        {"shell": "restart everything"},
    ],
)
def test_invalid_arguments_are_rejected_before_tool_execution(arguments):
    with pytest.raises(ValueError):
        run([decision(arguments)])


def test_hallucinated_evidence_cannot_support_a_conclusion():
    with pytest.raises(ValueError, match="nonexistent evidence"):
        run(
            [
                decision(
                    next_tool=None,
                    evidence_sufficient=True,
                    hypotheses=(
                        {
                            "claim": "Restart is safe",
                            "status": "supported",
                            "supporting_evidence_ids": ("invented-status",),
                        },
                    ),
                )
            ]
        )


def test_terminal_decision_cannot_target_undiscovered_service():
    with pytest.raises(ValueError, match="undiscovered service"):
        run([decision(next_tool=None, evidence_sufficient=True, relevant_service="unknown")])


def test_full_tool_budget_finishes_without_langgraph_recursion_failure():
    _, _, result = run([decision({"limit": limit}) for limit in range(1, 10)])
    assert result["tool_calls"] == 8
    assert result["recommendation"]["action"] is None
    assert len(result["decision_trace"]) == 9


def test_string_false_is_not_human_approval():
    graph, config, result = run(
        [
            decision(
                next_tool={
                    "name": "get_service_status",
                    "arguments": {},
                    "purpose": "Confirm state",
                }
            ),
            decision(next_tool=None, evidence_sufficient=True),
        ]
    )
    assert result["__interrupt__"]
    result = graph.invoke(Command(resume={"approved": "false", "actor": "operator"}), config)
    assert result["status"] == "rejected"
    assert result.get("execution_result") is None
