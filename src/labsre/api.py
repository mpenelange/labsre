from __future__ import annotations

from typing import Any
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException
from langgraph.types import Command
from pydantic import BaseModel, Field

from labsre.models import ApprovalDecision
from labsre.runtime import graph

app = FastAPI(title="LabSRE", version="0.1.0")


class InvestigationRequest(BaseModel):
    scenario_id: str = Field(pattern=r"^[a-z0-9-]+$")
    objective: str = Field(min_length=3, max_length=500)
    service: str = "immich_server"


def serialize_result(result: dict[str, Any], thread_id: str) -> dict[str, Any]:
    interrupts = result.get("__interrupt__", [])
    return {
        "thread_id": thread_id,
        "status": "awaiting_approval" if interrupts else result.get("status", "completed"),
        "recommendation": result.get("recommendation"),
        "interrupts": [item.value for item in interrupts],
        "execution_result": result.get("execution_result"),
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "replay"}


@app.post("/incidents/investigate")
def investigate(request: InvestigationRequest) -> dict[str, Any]:
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    try:
        result = graph.invoke(
            {
                "incident_id": thread_id,
                "scenario_id": request.scenario_id,
                "objective": request.objective,
                "service": request.service,
                "status": "new",
            },
            config=config,
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return serialize_result(result, thread_id)


@app.post("/incidents/{thread_id}/decision")
def decide(thread_id: str, decision: ApprovalDecision) -> dict[str, Any]:
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = graph.get_state(config)
    if not snapshot.next:
        raise HTTPException(
            status_code=404, detail="incident not found or is not awaiting a decision"
        )
    result = graph.invoke(Command(resume=decision.model_dump()), config=config)
    return serialize_result(result, thread_id)


def main() -> None:
    uvicorn.run("labsre.api:app", host="0.0.0.0", port=8000)
