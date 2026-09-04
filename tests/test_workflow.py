from pathlib import Path

from langgraph.types import Command

from labsre.replay import ReplayGateway
from labsre.workflow import build_graph

SCENARIOS = Path(__file__).parents[1] / "scenarios"


def initial_state(scenario_id: str) -> dict:
    return {
        "incident_id": f"test-{scenario_id}",
        "scenario_id": scenario_id,
        "objective": "Diagnose why Immich is unavailable",
        "service": "immich_server",
        "status": "new",
    }


def test_workflow_pauses_then_executes_approved_action() -> None:
    gateway = ReplayGateway(SCENARIOS)
    graph = build_graph(gateway)
    config = {"configurable": {"thread_id": "approved-case"}}

    pending = graph.invoke(initial_state("immich-restart-loop"), config=config)
    assert pending["__interrupt__"]
    assert pending["recommendation"]["action"]["target"] == "immich_server"

    resolved = graph.invoke(
        Command(resume={"approved": True, "actor": "test-operator"}), config=config
    )
    assert resolved["status"] == "resolved"
    assert resolved["execution_result"]["status"] == "completed"


def test_workflow_does_not_execute_rejected_action() -> None:
    gateway = ReplayGateway(SCENARIOS)
    graph = build_graph(gateway)
    config = {"configurable": {"thread_id": "rejected-case"}}

    graph.invoke(initial_state("immich-restart-loop"), config=config)
    rejected = graph.invoke(
        Command(resume={"approved": False, "actor": "test-operator"}), config=config
    )

    assert rejected["status"] == "rejected"
    assert "execution_result" not in rejected
    assert gateway.get_service_status("immich-restart-loop", "immich_server").health == "unhealthy"


def test_workflow_abstains_when_evidence_is_insufficient() -> None:
    gateway = ReplayGateway(SCENARIOS)
    graph = build_graph(gateway)
    config = {"configurable": {"thread_id": "unknown-case"}}

    result = graph.invoke(initial_state("immich-unknown-failure"), config=config)

    assert result["status"] == "needs_human_investigation"
    assert result["recommendation"]["action"] is None
    assert "__interrupt__" not in result
