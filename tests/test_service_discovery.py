import json
from pathlib import Path

import pytest

from labsre.replay import ReplayGateway


def _write_scenario(directory: Path) -> None:
    scenario = {
        "scenario_id": "discovery",
        "services": {
            "photos": {
                "service": "photos",
                "state": "running",
                "health": "unhealthy",
                "restart_count": 2,
                "observed_at": "2026-09-04T12:00:00Z",
            },
            "photos_db": {
                "service": "photos_db",
                "state": "running",
                "health": "healthy",
                "observed_at": "2026-09-04T12:00:00Z",
            },
        },
        "service_catalog": {
            "photos": {
                "service": "photos",
                "display_name": "Photo Library",
                "description": "User-facing photo application",
                "project": "media",
                "criticality": "medium",
                "user_facing": True,
                "dependencies": ["photos_db"],
                "tags": ["photos"],
            }
        },
        "dependencies": {
            "photos": [
                {"service": "photos", "dependency": "cache", "required": False}
            ]
        },
        "events": {
            "photos": [
                {
                    "service": "photos",
                    "timestamp": "2026-09-04T11:58:00Z",
                    "event_type": "restart",
                    "message": "container restarted",
                },
                {
                    "service": "photos",
                    "timestamp": "2026-09-04T11:59:00Z",
                    "event_type": "health_status",
                    "message": "health changed to unhealthy",
                },
            ]
        },
        "logs": {},
        "filesystems": [],
        "allowed_actions": {"restart_service": []},
    }
    (directory / "discovery.json").write_text(json.dumps(scenario))


def test_discovers_runtime_services_enriched_by_catalog(tmp_path: Path) -> None:
    _write_scenario(tmp_path)
    gateway = ReplayGateway(tmp_path)

    services = gateway.list_services("discovery")

    assert [service.service for service in services] == ["photos", "photos_db"]
    assert services[0].display_name == "Photo Library"
    assert services[0].dependencies == ["photos_db", "cache"]
    assert services[1].criticality == "unknown"


def test_dependencies_and_recent_events_are_bounded(tmp_path: Path) -> None:
    _write_scenario(tmp_path)
    gateway = ReplayGateway(tmp_path)

    dependencies = gateway.get_service_dependencies("discovery", "photos")
    events = gateway.get_recent_events("discovery", "photos", limit=1)

    assert {item.dependency for item in dependencies} == {"photos_db", "cache"}
    assert events[0].event_type == "health_status"
    with pytest.raises(ValueError, match="between 1 and 100"):
        gateway.get_recent_events("discovery", "photos", limit=101)


def test_discovery_rejects_unknown_service(tmp_path: Path) -> None:
    _write_scenario(tmp_path)
    gateway = ReplayGateway(tmp_path)

    with pytest.raises(KeyError, match="unknown service"):
        gateway.get_recent_events("discovery", "not-real")
