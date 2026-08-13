#!/usr/bin/env python3
"""Contract tests for the active decision-tree bundle and result files."""

from __future__ import annotations

import json
from pathlib import Path

from decision_trees.config.paths import BUNDLE_PATH, PROJECT_ROOT
from decision_trees.runtime.validate_decision_tree_bundle import validate_bundle


ACTIVE_TREE_IDS = {
    "bp_diagnosis",
    "bp_thresholds_targets",
    "optimized_hypertension_treatment",
    "hypertension_risk_stratification",
    "uncontrolled_resistant_hypertension",
}
RESULTS_DIR = PROJECT_ROOT / "results"


def test_active_bundle_contract() -> None:
    summary = validate_bundle(BUNDLE_PATH)
    assert summary["trees"] == 5
    bundle = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    assert {tree["id"] for tree in bundle["trees"]} == ACTIVE_TREE_IDS
    assert all(target in ACTIVE_TREE_IDS for tree in bundle["trees"] for target in tree.get("linksTo", []))


def test_result_files_match_active_trees() -> None:
    result_paths = {path.stem: path for path in RESULTS_DIR.glob("*.json")}
    assert set(result_paths) == ACTIVE_TREE_IDS
    for tree_id, path in result_paths.items():
        wrapper = json.loads(path.read_text(encoding="utf-8"))
        result = wrapper["result"]
        assert wrapper["treeId"] == tree_id
        assert result["status"] == "completed"
        assert result["entryTreeId"] == tree_id
        assert result["sourceRefs"]


def test_output_nodes_use_only_current_assignments() -> None:
    bundle = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    obsolete = {"treatment.targetProfile", "treatment.controlWindowMonths"}

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield key
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    assert not obsolete.intersection(walk(bundle))
    thresholds = next(tree for tree in bundle["trees"] if tree["id"] == "bp_thresholds_targets")
    assert thresholds["inputVariables"] == [
        "bp.category",
        "encounter.number",
        "comorbidity.targetOrganDamageOrCvd",
    ]
    assert not any(node["id"] == "threshold_hypertension" for node in thresholds["nodes"])
    assert not any(
        node.get("logic", {}).get("predicate", {}).get("field")
        in {"risk.class", "treatment.hasHighRiskComorbidity"}
        for node in thresholds["nodes"]
    )
    assert sum(
        node.get("logic", {}).get("predicate", {}).get("field")
        == "comorbidity.targetOrganDamageOrCvd"
        for node in thresholds["nodes"]
    ) == 1
    assert not any(
        predicate.get("op") == "in"
        and predicate.get("field") == "bp.category"
        and predicate.get("value") == ["hypertension", "grade1", "grade2"]
        for node in thresholds["nodes"]
        for predicate in [node.get("logic", {}).get("predicate", {})]
    )
    resistant = next(tree for tree in bundle["trees"] if tree["id"] == "uncontrolled_resistant_hypertension")
    assert not any(
        node.get("logic", {}).get("predicate", {}).get("field") == "medication.currentHasUnmappedDrug"
        for node in resistant["nodes"]
    )
    assert "medication.currentHasUnmappedDrug" not in resistant["inputVariables"]
    variables = {variable["id"]: variable for variable in bundle["variables"]}
    assert variables["medication.regimenStableWeeks"]["sourceSystem"] == "derived"
    assert variables["medication.regimenStableWeeks"]["derivedFrom"] == ["medication.regimenStartDate"]
    assert variables["medication.regimenStartDate"]["sourceSystem"] == "medication"
    assert "medication.regimenStableWeeks" in resistant["inputVariables"]
    stable_node = next(node for node in resistant["nodes"] if node["id"] == "resistant_stable")
    assert stable_node["logic"]["predicate"] == {
        "field": "medication.regimenStableWeeks",
        "op": "gte",
        "value": 4,
    }
    assert "không nhập số tuần" in stable_node["display"]["detail"]
    resistant_range = next(node for node in resistant["nodes"] if node["id"] == "resistant_range")
    assert all(
        item.get("field") != "bp.latest.diastolicMmHg" or item.get("op") != "present"
        for item in resistant_range["logic"]["predicate"]["all"]
    )
    assert "present" not in resistant_range["display"].get("detail", "")
    for tree in bundle["trees"]:
        for node in tree["nodes"]:
            assignments = node.get("data", {}).get("sets", {})
            if node["type"] not in {"inference", "end"} or not assignments:
                continue
            detail = node.get("display", {}).get("detail", "")
            for field, value in assignments.items():
                expected = f"{field} = {str(value).lower() if isinstance(value, bool) else value}"
                assert expected in detail


def test_exported_variable_catalog_preserves_derived_regimen_duration() -> None:
    catalog_path = PROJECT_ROOT / "decision_trees" / "trees" / "clinical_variables.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    variables = {variable["id"]: variable for variable in catalog["variables"]}
    assert variables["medication.regimenStartDate"]["sourceSystem"] == "medication"
    assert variables["medication.regimenStableWeeks"]["sourceSystem"] == "derived"
    assert variables["medication.regimenStableWeeks"]["derivedFrom"] == ["medication.regimenStartDate"]
    contract = json.loads(
        (PROJECT_ROOT / "decision_trees" / "contracts" / "clinical_variables.json").read_text(encoding="utf-8")
    )
    assert "medication.regimenStableWeeks" in contract["inputForm"]["derivedPresentation"]["fields"]
