from __future__ import annotations

from typing import Protocol

from labsre.models import (
    DiscoveredService,
    ExecutionResult,
    FilesystemUsage,
    LogEvent,
    ServiceDependency,
    ServiceEvent,
    ServiceStatus,
)


class OperationsGateway(Protocol):
    def list_services(self, scenario_id: str) -> list[DiscoveredService]: ...

    def get_service_status(self, scenario_id: str, service: str) -> ServiceStatus: ...

    def get_service_dependencies(
        self, scenario_id: str, service: str
    ) -> list[ServiceDependency]: ...

    def get_recent_events(
        self, scenario_id: str, service: str, limit: int = 50
    ) -> list[ServiceEvent]: ...

    def get_service_logs(self, scenario_id: str, service: str) -> list[LogEvent]: ...

    def get_filesystem_usage(self, scenario_id: str) -> list[FilesystemUsage]: ...

    def get_permitted_actions(self, scenario_id: str, service: str) -> list[str]: ...

    def restart_service(self, scenario_id: str, service: str) -> ExecutionResult: ...
