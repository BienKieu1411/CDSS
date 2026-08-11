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
