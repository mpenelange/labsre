from __future__ import annotations

import os
from pathlib import Path

from labsre.replay import ReplayGateway
from labsre.workflow import build_graph


def scenario_dir() -> Path:
    configured = os.getenv("LABSRE_SCENARIO_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "scenarios"


gateway = ReplayGateway(scenario_dir())
graph = build_graph(gateway)
