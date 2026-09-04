from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from labsre.approval import action_digest
from labsre.gateway import OperationsGateway
from labsre.models import Evidence, ProposedAction, Recommendation


class IncidentState(TypedDict, total=False):
    incident_id: str
    scenario_id: str
    objective: str
    service: str
    evidence: list[dict[str, Any]]
    recommendation: dict[str, Any]
    approval_digest: str
    approval_actor: str
    status: str
    execution_result: dict[str, Any]


def build_graph(gateway: OperationsGateway):
    def scope_incident(state: IncidentState) -> dict[str, Any]:
        # The replay milestone scopes objectives to one explicit service. An LLM planner will
        # replace this policy only after it can be evaluated against deterministic cases.
        return {"status": "investigating"}

    def investigate(state: IncidentState) -> dict[str, Any]:
        scenario_id = state["scenario_id"]
        service = state["service"]
        status = gateway.get_service_status(scenario_id, service)
        logs = gateway.get_service_logs(scenario_id, service)
        filesystems = gateway.get_filesystem_usage(scenario_id)
        evidence = [
            Evidence(
                source="get_service_status",
                summary=(
                    f"{service} is {status.state}; health={status.health}; "
                    f"restarts={status.restart_count}"
                ),
                observed_at=status.observed_at,
                data=status.model_dump(mode="json"),
            ),
            Evidence(
                source="get_service_logs",
                summary=f"Retrieved {len(logs)} bounded log events for {service}",
                observed_at=logs[-1].timestamp if logs else status.observed_at,
                data={"events": [event.model_dump(mode="json") for event in logs]},
            ),
            Evidence(
                source="get_filesystem_usage",
                summary="Checked host filesystem pressure",
                observed_at=filesystems[0].observed_at,
                data={"filesystems": [fs.model_dump(mode="json") for fs in filesystems]},
            ),
        ]
        return {"evidence": [item.model_dump(mode="json") for item in evidence]}

    def recommend(state: IncidentState) -> dict[str, Any]:
        evidence = [Evidence.model_validate(item) for item in state["evidence"]]
        log_text = " ".join(
            event["message"] for item in evidence for event in item.data.get("events", [])
        ).lower()
        max_disk = max(
            (fs["used_percent"] for item in evidence for fs in item.data.get("filesystems", [])),
            default=0,
        )
        disk_related = max_disk >= 90 and ("space" in log_text or "disk" in log_text)
        diagnosis = (
            "Service restart loop is correlated with critical disk pressure"
            if disk_related
            else (
                "Service is unhealthy; available evidence does not establish "
                "disk pressure as the cause"
            )
        )
        action = ProposedAction(
            action="restart_service",
            target=state["service"],
            rationale=(
                "Restart the allowlisted stateless service after the underlying "
                "condition is cleared"
            ),
            risk="brief service interruption; restart may not resolve the underlying condition",
        )
        recommendation = Recommendation(
            diagnosis=diagnosis,
            confidence=0.95 if disk_related else 0.45,
            evidence=evidence,
            action=action if disk_related else None,
            requires_approval=True,
        )
        update: dict[str, Any] = {"recommendation": recommendation.model_dump(mode="json")}
        if recommendation.action:
            update["approval_digest"] = action_digest(state["incident_id"], recommendation.action)
        return update

    def route_recommendation(state: IncidentState) -> Literal["approval", "stop"]:
        return "approval" if state["recommendation"].get("action") else "stop"

    def request_approval(state: IncidentState) -> Command[Literal["execute", "stop"]]:
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
        if approved and not actor:
            return Command(update={"status": "rejected"}, goto="stop")
        return Command(
            update={"status": "approved" if approved else "rejected", "approval_actor": actor},
            goto="execute" if approved else "stop",
        )

    def execute(state: IncidentState) -> dict[str, Any]:
        action = ProposedAction.model_validate(state["recommendation"]["action"])
        expected = action_digest(state["incident_id"], action)
        if expected != state["approval_digest"]:
            raise PermissionError("action no longer matches the approved digest")
        result = gateway.restart_service(state["scenario_id"], action.target)
        return {"execution_result": result.model_dump(mode="json"), "status": "executed"}

    def verify(state: IncidentState) -> dict[str, Any]:
        current = gateway.get_service_status(state["scenario_id"], state["service"])
        return {"status": "resolved" if current.health == "healthy" else "unresolved"}

    def stop(state: IncidentState) -> dict[str, Any]:
        current = state.get("status")
        if current in {"approved", "rejected"}:
            return {"status": current}
        return {"status": "needs_human_investigation"}

    builder = StateGraph(IncidentState)
    builder.add_node("scope", scope_incident)
    builder.add_node("investigate", investigate)
    builder.add_node("recommend", recommend)
    builder.add_node("approval", request_approval)
    builder.add_node("execute", execute)
    builder.add_node("verify", verify)
    builder.add_node("stop", stop)
    builder.add_edge(START, "scope")
    builder.add_edge("scope", "investigate")
    builder.add_edge("investigate", "recommend")
    builder.add_conditional_edges("recommend", route_recommendation)
    builder.add_edge("execute", "verify")
    builder.add_edge("verify", END)
    builder.add_edge("stop", END)
    return builder.compile(checkpointer=InMemorySaver())
