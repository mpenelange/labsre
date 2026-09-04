import json
from pathlib import Path

import pytest

from labsre.evaluate import evaluate_case
from labsre.planner import HeuristicPlanner

ROOT = Path(__file__).parents[1]
CASES = json.loads((ROOT / "evaluations/cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["scenario_id"])
def test_behavioral_acceptance(case):
    result = evaluate_case(case, ROOT / "scenarios", HeuristicPlanner())
    assert result["passed"], result


def test_evaluation_detects_wrong_ground_truth():
    case = {**CASES[0], "service": "paperless_db"}
    result = evaluate_case(case, ROOT / "scenarios", HeuristicPlanner())
    assert not result["passed"]
    assert not result["checks"]["service_selection"]
