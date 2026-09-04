from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from labsre.models import (
    DiscoveredService,
    ExecutionResult,
    FilesystemUsage,
    LogEvent,
    ServiceDependency,
    ServiceEvent,
    ServiceStatus,
)


class HttpMcpGateway:
    """Operations gateway whose every capability crosses MCP Streamable HTTP."""

    def __init__(self, url: str) -> None:
        if not url.startswith(("http://", "https://")):
            raise ValueError("MCP URL must use HTTP or HTTPS")
        self._url = url

    def list_services(self, scenario_id: str) -> list[DiscoveredService]:
        result = self._call_tool("list_services", {"scenario_id": scenario_id})
        return [DiscoveredService.model_validate(item) for item in result]

    def get_service_status(self, scenario_id: str, service: str) -> ServiceStatus:
        result = self._call_tool(
            "get_service_status", {"scenario_id": scenario_id, "service": service}
        )
        return ServiceStatus.model_validate(result)

    def get_service_dependencies(
        self, scenario_id: str, service: str
    ) -> list[ServiceDependency]:
        result = self._call_tool(
            "get_service_dependencies", {"scenario_id": scenario_id, "service": service}
        )
        return [ServiceDependency.model_validate(item) for item in result]

    def get_recent_events(
        self, scenario_id: str, service: str, limit: int = 50
    ) -> list[ServiceEvent]:
        result = self._call_tool(
            "get_recent_events",
            {"scenario_id": scenario_id, "service": service, "limit": limit},
        )
        return [ServiceEvent.model_validate(item) for item in result]

    def get_service_logs(self, scenario_id: str, service: str) -> list[LogEvent]:
        result = self._call_tool(
            "get_service_logs", {"scenario_id": scenario_id, "service": service}
        )
        return [LogEvent.model_validate(item) for item in result]

    def get_filesystem_usage(self, scenario_id: str) -> list[FilesystemUsage]:
        result = self._call_tool("get_filesystem_usage", {"scenario_id": scenario_id})
        return [FilesystemUsage.model_validate(item) for item in result]

    def get_permitted_actions(self, scenario_id: str, service: str) -> list[str]:
        result = self._call_tool(
            "get_permitted_actions", {"scenario_id": scenario_id, "service": service}
        )
        return [str(item) for item in result]

    def restart_service(self, scenario_id: str, service: str) -> ExecutionResult:
        result = self._call_tool(
            "restart_service", {"scenario_id": scenario_id, "service": service}
        )
        return ExecutionResult.model_validate(result)

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return asyncio.run(self._call_tool_async(name, arguments))

    async def _call_tool_async(self, name: str, arguments: dict[str, Any]) -> Any:
        async with (
            streamable_http_client(self._url) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            response = await session.call_tool(name, arguments)
            if response.isError:
                message = response.content[0].text if response.content else "MCP tool failed"
                raise RuntimeError(message)
            if response.structuredContent is not None:
                return response.structuredContent.get("result", response.structuredContent)
            if not response.content or not hasattr(response.content[0], "text"):
                raise RuntimeError(f"MCP tool {name} returned no JSON content")
            return json.loads(response.content[0].text)
