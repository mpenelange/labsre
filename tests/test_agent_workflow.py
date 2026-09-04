from pathlib import Path

from langgraph.types import Command

from labsre.agent_workflow import build_agent_graph
from labsre.planner import InvestigationDecision, ScriptedPlanner, ToolRequest
from labsre.replay import ReplayGateway

SCENARIOS = Path(__file__).parents[1] / "scenarios"


def test_agent_selects_tool_then_pauses_for_approved_remediation() -> None:
    planner = ScriptedPlanner(
        [
            InvestigationDecision(
                situation_summary="Paperless runtime state needs confirmation.",
                next_tool=ToolRequest(
                    name="get_service_status",
                    arguments={"service": "paperless_web"},
                    purpose="Confirm whether the application is stopped.",
                ),
                evidence_sufficient=False,
                relevant_service="paperless_web",
                confidence=0.3,
                reasoning_summary="Discovery indicates the application is degraded.",
            ),
            InvestigationDecision(
                situation_summary="Paperless is stopped while its database remains available.",
                next_tool=None,
                evidence_sufficient=True,
                relevant_service="paperless_web",
                confidence=0.96,
                reasoning_summary="Authoritative status confirms the application is stopped.",
            ),
        ]
    )
    gateway = ReplayGateway(SCENARIOS)
    graph = build_agent_graph(gateway, planner)
    config = {"configurable": {"thread_id": "dynamic-approved"}}
    pending = graph.invoke(
        {
            "incident_id": "dynamic-approved",
            "scenario_id": "service-stopped",
            "objective": "Why is my document service unavailable?",
            "status": "new",
        },
        config=config,
    )

    assert pending["__interrupt__"]
    assert pending["tool_calls"] == 1
    assert pending["recommendation"]["action"]["target"] == "paperless_web"
    assert len(planner.calls) == 2

    resolved = graph.invoke(
        Command(resume={"approved": True, "actor": "operator"}), config=config
    )
    assert resolved["status"] == "resolved"


def test_agent_budget_exhaustion_abstains() -> None:
    request = InvestigationDecision(
        situation_summary="More status evidence is requested.",
        next_tool=ToolRequest(
            name="get_service_status",
            arguments={"service": "dashboard"},
            purpose="Inspect dashboard status.",
        ),
        evidence_sufficient=False,
        relevant_service="dashboard",
        confidence=0.2,
        reasoning_summary="The current evidence is insufficient.",
    )
    gateway = ReplayGateway(SCENARIOS)
    graph = build_agent_graph(gateway, ScriptedPlanner([request]), max_tool_calls=0)
    result = graph.invoke(
        {
            "incident_id": "budget-case",
            "scenario_id": "ambiguous-service-failure",
            "objective": "Investigate the dashboard",
            "status": "new",
        },
        config={"configurable": {"thread_id": "budget-case"}},
    )

    assert result["status"] == "needs_human_investigation"
    assert result["tool_calls"] == 0
    assert result["recommendation"]["action"] is None
