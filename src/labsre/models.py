from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ServiceStatus(BaseModel):
    service: str
    state: str
    health: str | None = None
    restart_count: int = 0
    observed_at: str


class LogEvent(BaseModel):
    service: str
    timestamp: str
    severity: Severity
    message: str


class FilesystemUsage(BaseModel):
    host: str
    mount: str
    used_percent: float = Field(ge=0, le=100)
    available_gb: float = Field(ge=0)
    observed_at: str


class Evidence(BaseModel):
    source: str
    summary: str
    observed_at: str
    data: dict[str, Any] = Field(default_factory=dict)


class ProposedAction(BaseModel):
    action: str
    target: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    rationale: str
    risk: str


class Recommendation(BaseModel):
    diagnosis: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence]
    action: ProposedAction | None = None
    requires_approval: bool = True


class ApprovalDecision(BaseModel):
    approved: bool
    actor: str = Field(min_length=1)


class ExecutionResult(BaseModel):
    action: str
    target: str
    status: str
    message: str


class Scenario(BaseModel):
    scenario_id: str
    services: dict[str, ServiceStatus]
    logs: dict[str, list[LogEvent]]
    filesystems: list[FilesystemUsage]
    allowed_actions: dict[str, list[str]]
