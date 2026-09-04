from pathlib import Path

import pytest

from labsre.models import Scenario

SCENARIOS = Path(__file__).parents[1] / "scenarios"

GENERIC_SCENARIOS = {
    "service-stopped": {"paperless_web": ("exited", "unhealthy")},
    "unhealthy-dependency": {
        "homeassistant": ("running", "unhealthy"),
        "mqtt": ("restarting", "unhealthy"),
    },
    "routing-failure": {
        "forgejo": ("running", "healthy"),
        "traefik": ("running", "unhealthy"),
    },
    "ambiguous-service-failure": {
        "dashboard": ("running", "unhealthy"),
        "dashboard_db": ("running", "healthy"),
    },
}


@pytest.mark.parametrize(("scenario_id", "conditions"), GENERIC_SCENARIOS.items())
def test_generic_scenario_catalog_has_expected_service_conditions(
    scenario_id: str, conditions: dict[str, tuple[str, str]]
) -> None:
    scenario = Scenario.model_validate_json((SCENARIOS / f"{scenario_id}.json").read_text())

    assert scenario.scenario_id == scenario_id
    assert scenario.filesystems
    assert set(conditions) <= scenario.services.keys()
    assert set(conditions) <= scenario.service_catalog.keys()
    for service, (state, health) in conditions.items():
        status = scenario.services[service]
        assert status.service == service
        assert (status.state, status.health) == (state, health)


def test_routing_failure_distinguishes_app_health_from_proxy_health() -> None:
    scenario = Scenario.model_validate_json((SCENARIOS / "routing-failure.json").read_text())

    assert scenario.services["forgejo"].health == "healthy"
    assert scenario.services["traefik"].health == "unhealthy"
    assert scenario.dependencies["forgejo"][0].dependency == "traefik"
    assert any("no matching backend" in event.message for event in scenario.logs["traefik"])


def test_ambiguous_failure_does_not_allow_automatic_remediation() -> None:
    scenario = Scenario.model_validate_json(
        (SCENARIOS / "ambiguous-service-failure.json").read_text()
    )

    assert scenario.allowed_actions["restart_service"] == []
    assert all(usage.used_percent < 90 for usage in scenario.filesystems)
    assert scenario.services["dashboard_db"].health == "healthy"
    assert scenario.events == {}
