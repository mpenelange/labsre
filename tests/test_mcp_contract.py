import json

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_mcp_exposes_bounded_diagnostic_tools() -> None:
    parameters = StdioServerParameters(command="labsre-mcp")
    async with (
        stdio_client(parameters) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        names = {tool.name for tool in tools.tools}
        assert names == {
            "get_service_status",
            "get_service_logs",
            "get_filesystem_usage",
            "restart_service",
        }

        result = await session.call_tool(
            "get_service_status",
            {"scenario_id": "immich-restart-loop", "service": "immich_server"},
        )
        assert not result.isError
        payload = json.loads(result.content[0].text)
        assert payload["health"] == "unhealthy"
