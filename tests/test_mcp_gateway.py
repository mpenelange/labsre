from typing import Any

from labsre.mcp_gateway import HttpMcpGateway
from labsre.runtime import build_gateway


def test_http_gateway_maps_protocol_payloads_to_domain_models(monkeypatch) -> None:
    gateway = HttpMcpGateway("http://mcp.test/mcp")
    responses: dict[str, Any] = {
        "list_services": [
            {
                "service": "photos",
                "state": "running",
                "health": "healthy",
                "restart_count": 0,
                "observed_at": "2026-09-04T00:00:00Z",
            }
        ],
        "get_permitted_actions": ["restart_service"],
    }
    monkeypatch.setattr(gateway, "_call_tool", lambda name, arguments: responses[name])

    services = gateway.list_services("test")
    permitted = gateway.get_permitted_actions("test", "photos")

    assert services[0].service == "photos"
    assert services[0].health == "healthy"
    assert permitted == ["restart_service"]


def test_http_gateway_rejects_non_http_transport() -> None:
    try:
        HttpMcpGateway("stdio://labsre-mcp")
    except ValueError as exc:
        assert "HTTP" in str(exc)
    else:
        raise AssertionError("non-HTTP MCP URL was accepted")


def test_explicit_mcp_url_takes_precedence_over_local_docker_mode(monkeypatch) -> None:
    monkeypatch.setenv("LABSRE_MODE", "docker-readonly")
    monkeypatch.setenv("LABSRE_MCP_URL", "http://mcp.test/mcp")

    assert isinstance(build_gateway(), HttpMcpGateway)
