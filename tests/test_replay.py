from pathlib import Path

import pytest

from labsre.replay import ReplayGateway

SCENARIOS = Path(__file__).parents[1] / "scenarios"


def test_replay_restart_is_allowlisted() -> None:
    gateway = ReplayGateway(SCENARIOS)
    result = gateway.restart_service("immich-restart-loop", "immich_server")
    assert result.status == "completed"
    assert gateway.get_service_status("immich-restart-loop", "immich_server").health == "healthy"


def test_replay_rejects_unknown_restart_target() -> None:
    gateway = ReplayGateway(SCENARIOS)
    with pytest.raises(PermissionError):
        gateway.restart_service("immich-restart-loop", "immich_postgres")
