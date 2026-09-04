from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from labsre.models import (
    DiscoveredService,
    ExecutionResult,
    FilesystemUsage,
    LogEvent,
    Scenario,
    ServiceDependency,
    ServiceEvent,
    ServiceStatus,
)


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

    def list_services(self, scenario_id: str) -> list[DiscoveredService]:
        scenario = self._load(scenario_id)
        discovered: list[DiscoveredService] = []
        for name, status in sorted(scenario.services.items()):
            catalog = scenario.service_catalog.get(name)
            explicit_dependencies = scenario.dependencies.get(name, [])
            dependency_names = [item.dependency for item in explicit_dependencies]
            if catalog:
                dependency_names = list(dict.fromkeys([*catalog.dependencies, *dependency_names]))
            discovered.append(
                DiscoveredService(
                    **status.model_dump(),
                    display_name=catalog.display_name if catalog else None,
                    description=catalog.description if catalog else None,
                    project=catalog.project if catalog else None,
                    criticality=catalog.criticality if catalog else "unknown",
                    user_facing=catalog.user_facing if catalog else False,
                    dependencies=dependency_names,
                    tags=catalog.tags if catalog else [],
                )
            )
        return deepcopy(discovered)

    def get_service_status(self, scenario_id: str, service: str) -> ServiceStatus:
        scenario = self._load(scenario_id)
        if service not in scenario.services:
            raise KeyError(f"unknown service: {service}")
        return deepcopy(scenario.services[service])

    def get_service_logs(self, scenario_id: str, service: str) -> list[LogEvent]:
        scenario = self._require_service(scenario_id, service)
        return deepcopy(scenario.logs.get(service, []))

    def get_service_dependencies(
        self, scenario_id: str, service: str
    ) -> list[ServiceDependency]:
        scenario = self._require_service(scenario_id, service)
        dependencies = list(scenario.dependencies.get(service, []))
        catalog = scenario.service_catalog.get(service)
        known = {item.dependency for item in dependencies}
        if catalog:
            dependencies.extend(
                ServiceDependency(service=service, dependency=name)
                for name in catalog.dependencies
                if name not in known
            )
        return deepcopy(dependencies)

    def get_recent_events(
        self, scenario_id: str, service: str, limit: int = 50
    ) -> list[ServiceEvent]:
        if not 1 <= limit <= 100:
            raise ValueError("event limit must be between 1 and 100")
        scenario = self._require_service(scenario_id, service)
        events = sorted(
            scenario.events.get(service, []), key=lambda item: item.timestamp, reverse=True
        )
        return deepcopy(events[:limit])

    def get_filesystem_usage(self, scenario_id: str) -> list[FilesystemUsage]:
        return deepcopy(self._load(scenario_id).filesystems)

    def get_permitted_actions(self, scenario_id: str, service: str) -> list[str]:
        scenario = self._require_service(scenario_id, service)
        return sorted(
            action
            for action, targets in scenario.allowed_actions.items()
            if service in targets
        )

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

    def _require_service(self, scenario_id: str, service: str) -> Scenario:
        scenario = self._load(scenario_id)
        if service not in scenario.services:
            raise KeyError(f"unknown service: {service}")
        return scenario
