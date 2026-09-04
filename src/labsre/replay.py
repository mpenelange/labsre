from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from labsre.models import ExecutionResult, FilesystemUsage, LogEvent, Scenario, ServiceStatus


class ReplayGateway:
    """Deterministic backend for development and evaluation; never touches a real host."""

    def __init__(self, scenario_dir: Path) -> None:
        self._scenario_dir = scenario_dir
        self._cache: dict[str, Scenario] = {}

    def _load(self, scenario_id: str) -> Scenario:
        if scenario_id not in self._cache:
            path = (self._scenario_dir / f"{scenario_id}.json").resolve()
            if path.parent != self._scenario_dir.resolve():
                raise ValueError("invalid scenario id")
            self._cache[scenario_id] = Scenario.model_validate_json(path.read_text())
        return self._cache[scenario_id]

    def reset(self, scenario_id: str) -> None:
        self._cache.pop(scenario_id, None)

    def get_service_status(self, scenario_id: str, service: str) -> ServiceStatus:
        scenario = self._load(scenario_id)
        if service not in scenario.services:
            raise KeyError(f"unknown service: {service}")
        return deepcopy(scenario.services[service])

    def get_service_logs(self, scenario_id: str, service: str) -> list[LogEvent]:
        scenario = self._load(scenario_id)
        return deepcopy(scenario.logs.get(service, []))

    def get_filesystem_usage(self, scenario_id: str) -> list[FilesystemUsage]:
        return deepcopy(self._load(scenario_id).filesystems)

    def restart_service(self, scenario_id: str, service: str) -> ExecutionResult:
        scenario = self._load(scenario_id)
        permitted = scenario.allowed_actions.get("restart_service", [])
        if service not in permitted:
            raise PermissionError(f"restart is not allowlisted for {service}")
        current = scenario.services[service]
        scenario.services[service] = current.model_copy(
            update={
                "state": "running",
                "health": "healthy",
                "restart_count": current.restart_count + 1,
            }
        )
        return ExecutionResult(
            action="restart_service",
            target=service,
            status="completed",
            message=f"Replay restart completed for {service}",
        )

    def export_scenario(self, scenario_id: str) -> str:
        return json.dumps(self._load(scenario_id).model_dump(mode="json"), indent=2)
