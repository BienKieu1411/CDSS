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
from decision_trees.pipeline.multi_agent_pipeline import (
    candidate_validation_errors,
    canonicalize_evidence_claims,
    evidence_variable_reference_errors,
    strict_verifier_errors,
)


def first_predicate_leaf(predicate: dict) -> dict:
    if "field" in predicate:
        return predicate
    for key in ("all", "any"):
        children = predicate.get(key)
        if isinstance(children, list):
            for child in children:
                return first_predicate_leaf(child)
    if "not" in predicate:
        return first_predicate_leaf(predicate["not"])
    raise AssertionError(f"predicate has no leaf: {predicate}")


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
    first_predicate_leaf(condition["logic"]["predicate"])["field"] = "bp.systolicMmHg"
    errors = candidate_validation_errors("bp_diagnosis", candidate, bundle)
    assert any("undeclared input variable bp.systolicMmHg" in error for error in errors)

    candidate = copy.deepcopy(next(tree for tree in bundle["trees"] if tree["id"] == "bp_diagnosis"))
    candidate["nodes"][0]["sourceRefs"][0]["sourceId"] = "image_05_uncontrolled_resistant"
    errors = candidate_validation_errors("bp_diagnosis", candidate, bundle)
    assert any("outside target evidence" in error for error in errors)

    evidence_bundle = {
        "variables": [
            {"id": "bp.systolicMmHg", "dataType": "number"},
            {"id": "bp.diastolicMmHg", "dataType": "number"},
            {"id": "bp.officeReadingCount", "dataType": "integer"},
            {"id": "laboratory.potassiumMmolL", "dataType": "number"},
        ]
    }
    evidence = {
        "claims": [{
            "claimId": "bp",
            "variablesJson": json.dumps([{"name": "HATT", "type": "number"}, {"name": "HATTr", "type": "number"}]),
            "predicateJson": json.dumps({"and": [{"between": ["HATT", 130, 139]}, {"between": ["HATTr", 85, 89]}]}),
        }]
    }
    normalized = canonicalize_evidence_claims(evidence, "bp_thresholds_targets", evidence_bundle)
    assert evidence_variable_reference_errors(normalized, evidence_bundle) == []
    assert normalized["claims"][0]["predicateJson"]
    lab_evidence = {
        "claims": [{
            "claimId": "lab",
            "variablesJson": json.dumps(["office_reading_count"]),
            "predicateJson": json.dumps({"office_reading_count": {"$gte": 2}}),
        }]
    }
    lab_normalized = canonicalize_evidence_claims(lab_evidence, "uncontrolled_resistant_hypertension", evidence_bundle)
    assert evidence_variable_reference_errors(lab_normalized, evidence_bundle) == []
    print("pipeline strict pass gate tests: ok")


if __name__ == "__main__":
    main()
