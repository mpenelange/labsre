from __future__ import annotations

import json
from typing import Any, Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from labsre.approval import action_digest
from labsre.gateway import OperationsGateway
from labsre.models import Evidence, ProposedAction, Recommendation
from labsre.planner import InvestigationDecision, Planner

READ_TOOLS = (
    "get_service_status",
    "get_service_dependencies",
    "get_recent_events",
    "get_service_logs",
    "get_filesystem_usage",
)


class AgentIncidentState(TypedDict, total=False):
    incident_id: str
    scenario_id: str
    objective: str
    preferred_service: str | None
    relevant_service: str
    evidence: list[dict[str, Any]]
    tool_history: list[str]
    tool_calls: int
    decision: dict[str, Any]
    recommendation: dict[str, Any]
    approval_digest: str
    approval_actor: str
    status: str
    execution_result: dict[str, Any]


def build_agent_graph(
    gateway: OperationsGateway,
    planner: Planner,
    *,
    max_tool_calls: int = 8,
):
    """Build a bounded agent loop; the planner can request only registered read tools."""

    def discover(state: AgentIncidentState) -> dict[str, Any]:
        services = gateway.list_services(state["scenario_id"])
        observed_at = max((item.observed_at for item in services), default="unknown")
        evidence = Evidence(
            source="list_services",
            summary=f"Discovered {len(services)} services",
            observed_at=observed_at,
            data={"services": [item.model_dump(mode="json") for item in services]},
        )
        return {
            "evidence": [evidence.model_dump(mode="json")],
            "tool_history": [],
            "tool_calls": 0,
            "status": "investigating",
        }

    def plan(state: AgentIncidentState) -> dict[str, Any]:
        objective = state["objective"]
        if state.get("preferred_service"):
            objective = f"{objective}\nOperator-supplied service hint: {state['preferred_service']}"
        decision = planner.decide(
            objective=objective,
            evidence=state["evidence"],
            available_tools=READ_TOOLS,
        )
        update: dict[str, Any] = {"decision": decision.model_dump(mode="json")}
        if decision.relevant_service:
            update["relevant_service"] = decision.relevant_service
        return update

    def route_plan(state: AgentIncidentState) -> Literal["tool", "recommend"]:
        decision = _decision_from_state(state["decision"])
        if decision.evidence_sufficient or decision.next_tool is None:
            return "recommend"
        if state["tool_calls"] >= max_tool_calls:
            return "recommend"
        return "tool"

    def call_tool(state: AgentIncidentState) -> dict[str, Any]:
        decision = _decision_from_state(state["decision"])
        request = decision.next_tool
        if request is None or request.name not in READ_TOOLS:
            raise ValueError("planner requested an unavailable diagnostic tool")
        signature = json.dumps(
            {"name": request.name, "arguments": request.arguments}, sort_keys=True
        )
        if signature in state["tool_history"]:
            raise ValueError("planner repeated an identical tool request")

        scenario_id = state["scenario_id"]
        discovered = state["evidence"][0]["data"]["services"]
        known_services = {item["service"] for item in discovered}
        service = str(request.arguments.get("service", state.get("relevant_service", "")))
        if request.name != "get_filesystem_usage" and service not in known_services:
            raise ValueError(f"planner targeted an undiscovered service: {service}")

        if request.name == "get_service_status":
            value: Any = gateway.get_service_status(scenario_id, service).model_dump(mode="json")
        elif request.name == "get_service_dependencies":
            value = [
                item.model_dump(mode="json")
                for item in gateway.get_service_dependencies(scenario_id, service)
            ]
        elif request.name == "get_recent_events":
            limit = int(request.arguments.get("limit", 50))
            value = [
                item.model_dump(mode="json")
                for item in gateway.get_recent_events(scenario_id, service, limit)
            ]
        elif request.name == "get_service_logs":
            value = [
                item.model_dump(mode="json")
                for item in gateway.get_service_logs(scenario_id, service)
            ]
        else:
            value = [
                item.model_dump(mode="json")
                for item in gateway.get_filesystem_usage(scenario_id)
            ]

        evidence = Evidence(
            source=request.name,
            summary=request.purpose,
            observed_at=_observation_time(value),
            data={"service": service or None, "result": value},
        )
        return {
            "evidence": [*state["evidence"], evidence.model_dump(mode="json")],
            "tool_history": [*state["tool_history"], signature],
            "tool_calls": state["tool_calls"] + 1,
        }

    def recommend(state: AgentIncidentState) -> dict[str, Any]:
        decision = _decision_from_state(state["decision"])
        evidence = [Evidence.model_validate(item) for item in state["evidence"]]
        service = state.get("relevant_service") or decision.relevant_service
        action = None
        if decision.evidence_sufficient and service:
            permitted = gateway.get_permitted_actions(state["scenario_id"], service)
            status = _status_for(evidence, service)
            degraded = status and (
                status.get("state") != "running" or status.get("health") not in {None, "healthy"}
            )
            if degraded and "restart_service" in permitted and decision.confidence >= 0.7:
                action = ProposedAction(
                    action="restart_service",
                    target=service,
                    rationale="Restart the allowlisted degraded service and verify its health",
                    risk="brief interruption; restart may not correct the underlying cause",
                )
        recommendation = Recommendation(
            diagnosis=decision.situation_summary,
            confidence=decision.confidence,
            evidence=evidence,
            action=action,
            requires_approval=action is not None,
        )
        update: dict[str, Any] = {
            "recommendation": recommendation.model_dump(mode="json")
        }
        if action:
            update["approval_digest"] = action_digest(state["incident_id"], action)
        else:
            update["status"] = "needs_human_investigation"
        return update

    def route_recommendation(state: AgentIncidentState) -> Literal["approval", "stop"]:
        return "approval" if state["recommendation"].get("action") else "stop"

    def request_approval(state: AgentIncidentState) -> Command[Literal["execute", "stop"]]:
        response = interrupt(
            {
                "question": "Approve this bounded remediation?",
                "incident_id": state["incident_id"],
                "action": state["recommendation"]["action"],
                "action_digest": state["approval_digest"],
                "diagnosis": state["recommendation"]["diagnosis"],
            }
        )
        approved = bool(response.get("approved"))
        actor = str(response.get("actor", "")).strip()
        return Command(
            update={
                "status": "approved" if approved and actor else "rejected",
                "approval_actor": actor,
            },
            goto="execute" if approved and actor else "stop",
        )

    def execute(state: AgentIncidentState) -> dict[str, Any]:
        action = ProposedAction.model_validate(state["recommendation"]["action"])
        if action_digest(state["incident_id"], action) != state["approval_digest"]:
            raise PermissionError("action no longer matches the approved digest")
        if action.action != "restart_service":
            raise PermissionError("unsupported remediation")
        result = gateway.restart_service(state["scenario_id"], action.target)
        return {"execution_result": result.model_dump(mode="json"), "status": "executed"}

    def verify(state: AgentIncidentState) -> dict[str, Any]:
        current = gateway.get_service_status(state["scenario_id"], state["relevant_service"])
        return {"status": "resolved" if current.health == "healthy" else "unresolved"}

    def stop(state: AgentIncidentState) -> dict[str, Any]:
        return {"status": state.get("status", "needs_human_investigation")}

    builder = StateGraph(AgentIncidentState)
    builder.add_node("discover", discover)
    builder.add_node("plan", plan)
    builder.add_node("tool", call_tool)
    builder.add_node("recommend", recommend)
    builder.add_node("approval", request_approval)
    builder.add_node("execute", execute)
    builder.add_node("verify", verify)
    builder.add_node("stop", stop)
    builder.add_edge(START, "discover")
    builder.add_edge("discover", "plan")
    builder.add_conditional_edges("plan", route_plan)
    builder.add_edge("tool", "plan")
    builder.add_conditional_edges("recommend", route_recommendation)
    builder.add_edge("execute", "verify")
    builder.add_edge("verify", END)
    builder.add_edge("stop", END)
    return builder.compile(checkpointer=InMemorySaver())


def _observation_time(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("observed_at", "unknown"))
    if isinstance(value, list) and value:
        return str(value[0].get("timestamp") or value[0].get("observed_at") or "unknown")
    return "unknown"


def _decision_from_state(value: dict[str, Any]) -> InvestigationDecision:
    return InvestigationDecision.model_validate_json(json.dumps(value))


def _status_for(evidence: list[Evidence], service: str) -> dict[str, Any] | None:
    for item in reversed(evidence):
        if item.source == "get_service_status" and item.data.get("service") == service:
            result = item.data.get("result")
            return result if isinstance(result, dict) else None
    return None
