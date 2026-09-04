from __future__ import annotations

from typing import Protocol

from labsre.models import ExecutionResult, FilesystemUsage, LogEvent, ServiceStatus


class OperationsGateway(Protocol):
    def get_service_status(self, scenario_id: str, service: str) -> ServiceStatus: ...

    def get_service_logs(self, scenario_id: str, service: str) -> list[LogEvent]: ...

    def get_filesystem_usage(self, scenario_id: str) -> list[FilesystemUsage]: ...

    def restart_service(self, scenario_id: str, service: str) -> ExecutionResult: ...
