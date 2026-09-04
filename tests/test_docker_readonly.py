from datetime import UTC, datetime

import pytest

from labsre.docker_readonly import DockerReadOnlyGateway

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def test_discovers_services_without_exposing_configuration() -> None:
    calls = []

    def runner(arguments: list[str]) -> str:
        calls.append(arguments)
        if arguments[1] == "ps":
            return "photos\trunning\tUp 2 hours (healthy)\tphotos:v1\tmedia\n"
        return "3\n"

    gateway = DockerReadOnlyGateway(runner=runner, now=lambda: NOW)
    services = gateway.list_services("live")

    assert services[0].service == "photos"
    assert services[0].health == "healthy"
    assert services[0].restart_count == 3
    assert all("Config.Env" not in " ".join(call) for call in calls)


def test_logs_are_bounded_and_secrets_are_redacted() -> None:
    def runner(arguments: list[str]) -> str:
        return "2026-09-04T11:59:00Z ERROR password=hunter2 token=abc123 request failed\n"

    gateway = DockerReadOnlyGateway(runner=runner, now=lambda: NOW)

    logs = gateway.get_service_logs("live", "photos")

    assert logs[0].severity == "warning"
    assert "hunter2" not in logs[0].message
    assert "abc123" not in logs[0].message
    assert "[REDACTED]" in logs[0].message


def test_live_remediation_is_always_disabled() -> None:
    gateway = DockerReadOnlyGateway(runner=lambda arguments: "", now=lambda: NOW)

    assert gateway.get_permitted_actions("live", "photos") == []
    with pytest.raises(PermissionError, match="disabled"):
        gateway.restart_service("live", "photos")


def test_service_name_cannot_inject_cli_arguments() -> None:
    gateway = DockerReadOnlyGateway(runner=lambda arguments: "", now=lambda: NOW)

    with pytest.raises(ValueError, match="invalid"):
        gateway.get_service_status("live", "photos; rm -rf data")
