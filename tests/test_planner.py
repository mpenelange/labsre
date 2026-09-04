from __future__ import annotations

import pytest
from pydantic import ValidationError

from labsre.planner import (
    HeuristicPlanner,
    Hypothesis,
    InvestigationDecision,
    Planner,
    ScriptedPlanner,
    ToolRequest,
)


def test_scripted_planner_returns_decisions_in_order_and_records_inputs() -> None:
    inspect = InvestigationDecision(
        situation_summary="The target service has not been inspected yet.",
        hypotheses=(Hypothesis(claim="The service may be stopped.", status="possible"),),
        next_tool=ToolRequest(
            name="get_service_status",
            arguments={"service": "photos"},
            purpose="Establish authoritative runtime state.",
        ),
        evidence_sufficient=False,
        relevant_service="photos",
        confidence=0.2,
        reasoning_summary="Runtime status is the next required observation.",
    )
    conclude = InvestigationDecision(
        situation_summary="The service is stopped.",
        hypotheses=(
            Hypothesis(
                claim="The service is stopped.",
                status="supported",
                supporting_evidence_ids=("status-1",),
            ),
        ),
        evidence_sufficient=True,
        relevant_service="photos",
        confidence=0.98,
        reasoning_summary="The service-status observation directly supports the conclusion.",
    )
    planner = ScriptedPlanner([inspect, conclude])

    first = planner.decide(
        objective="Find why photos is unavailable",
        evidence=[],
        available_tools=["get_service_status"],
    )
    second = planner.decide(
        objective="Find why photos is unavailable",
        evidence=[{"id": "status-1", "state": "stopped"}],
        available_tools=["get_service_status"],
    )

    assert isinstance(planner, Planner)
    assert first.next_tool == inspect.next_tool
    assert second.evidence_sufficient is True
    assert planner.calls[1]["evidence"] == [{"id": "status-1", "state": "stopped"}]
    assert planner.remaining == 0


def test_decision_rejects_tool_request_after_evidence_is_sufficient() -> None:
    with pytest.raises(ValidationError, match="cannot request another tool"):
        InvestigationDecision(
            situation_summary="Enough evidence exists.",
            next_tool=ToolRequest(
                name="get_service_logs",
                purpose="Fetch unnecessary logs.",
            ),
            evidence_sufficient=True,
            confidence=0.9,
            reasoning_summary="The observations already establish the state.",
        )


def test_models_forbid_unknown_fields_and_coercion() -> None:
    with pytest.raises(ValidationError):
        Hypothesis.model_validate(
            {"claim": "Disk is full.", "status": "possible", "private_chain_of_thought": "..."}
        )
    with pytest.raises(ValidationError):
        InvestigationDecision.model_validate(
            {
                "situation_summary": "Status unknown.",
                "evidence_sufficient": "false",
                "confidence": 0.1,
                "reasoning_summary": "Inspect status.",
            }
        )


def test_scripted_planner_rejects_an_unavailable_tool() -> None:
    planner = ScriptedPlanner(
        [
            {
                "situation_summary": "Logs may explain the failure.",
                "next_tool": {
                    "name": "get_service_logs",
                    "purpose": "Inspect recent bounded logs.",
                },
                "evidence_sufficient": False,
                "confidence": 0.3,
                "reasoning_summary": "Status alone does not establish a cause.",
            }
        ]
    )

    with pytest.raises(ValueError, match="unavailable tool"):
        planner.decide(
            objective="Diagnose the service",
            evidence=[],
            available_tools=["get_service_status"],
        )


def test_scripted_planner_fails_clearly_when_exhausted() -> None:
    planner = ScriptedPlanner([])

    with pytest.raises(RuntimeError, match="no decisions remaining"):
        planner.decide(objective="Diagnose", evidence=[], available_tools=[])


def test_heuristic_planner_selects_degraded_user_facing_service() -> None:
    planner = HeuristicPlanner()
    decision = planner.decide(
        objective="What is broken?",
        evidence=[
            {
                "source": "list_services",
                "data": {
                    "services": [
                        {
                            "service": "database",
                            "state": "running",
                            "health": "healthy",
                            "criticality": "high",
                            "user_facing": False,
                            "tags": [],
                        },
                        {
                            "service": "documents",
                            "state": "exited",
                            "health": "unhealthy",
                            "criticality": "medium",
                            "user_facing": True,
                            "tags": ["paperless"],
                        },
                    ]
                },
            }
        ],
        available_tools=["get_service_status"],
    )

    assert decision.relevant_service == "documents"
    assert decision.next_tool.name == "get_service_status"
