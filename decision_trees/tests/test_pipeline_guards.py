#!/usr/bin/env python3
"""Local tests for the strict pass gate and bounded feedback loop contract."""

import json
import sys
import copy
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decision_trees.config.paths import PASS_CRITERIA_PATH
from decision_trees.config.paths import BUNDLE_PATH
from decision_trees.pipeline.multi_agent_pipeline import candidate_validation_errors, strict_verifier_errors


def main() -> None:
    criteria = json.loads(PASS_CRITERIA_PATH.read_text(encoding="utf-8"))
    passing = {
        "status": "pass",
        "issues": [],
        "coverageJson": json.dumps({"coverageRatio": 1.0, "coveragePercentage": 100, "uncoveredClaims": []}),
        "missingDataJson": json.dumps({"missingVariables": [], "missingItems": []}),
    }
    assert strict_verifier_errors(passing, criteria) == []

    p2 = dict(passing)
    p2["issues"] = [{"severity": "P2", "message": "warning"}]
    assert strict_verifier_errors(p2, criteria)

    missing = dict(passing)
    missing["missingDataJson"] = json.dumps({"missingVariables": ["bp.systolicMmHg"]})
    assert strict_verifier_errors(missing, criteria)

    incomplete = dict(passing)
    incomplete["coverageJson"] = json.dumps({"coverageRatio": 1.0})
    assert strict_verifier_errors(incomplete, criteria)

    incomplete_missing = dict(passing)
    incomplete_missing["missingDataJson"] = json.dumps({"missingVariables": []})
    assert strict_verifier_errors(incomplete_missing, criteria)

    bundle = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    candidate = copy.deepcopy(next(tree for tree in bundle["trees"] if tree["id"] == "bp_diagnosis"))
    condition = next(node for node in candidate["nodes"] if node["type"] == "condition")
    condition["logic"]["predicate"]["all"][0]["field"] = "bp.systolicMmHg"
    errors = candidate_validation_errors("bp_diagnosis", candidate, bundle)
    assert any("undeclared input variable bp.systolicMmHg" in error for error in errors)

    candidate = copy.deepcopy(next(tree for tree in bundle["trees"] if tree["id"] == "bp_diagnosis"))
    candidate["nodes"][0]["sourceRefs"][0]["sourceId"] = "image_05_uncontrolled_resistant"
    errors = candidate_validation_errors("bp_diagnosis", candidate, bundle)
    assert any("outside target evidence" in error for error in errors)
    print("pipeline strict pass gate tests: ok")


if __name__ == "__main__":
    main()
