#!/usr/bin/env python3
"""Deterministic smoke tests for the five image-target decision trees."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decision_trees.config.paths import BUNDLE_PATH
from decision_trees.runtime.decision_tree_engine import MissingData, evaluate_predicate, run
from decision_trees.runtime.validate_decision_tree_bundle import validate_bundle


BUNDLE = BUNDLE_PATH


def assert_missing(predicate: dict, context: dict, expected: list[str]) -> None:
    try:
        evaluate_predicate(predicate, context)
    except MissingData as missing:
        assert list(missing.fields) == expected, (missing.fields, expected)
    else:
        raise AssertionError(f"expected missing data: {expected}")


def base_diagnosis() -> dict:
    return {
        "bp.measurementMethod": "office_3rd",
        "bp.office1.systolicMmHg": 130,
        "bp.office1.diastolicMmHg": 80,
        "bp.office1.targetOrganDamageOrCvd": False,
        "bp.office2.systolicMmHg": 130,
        "bp.office2.diastolicMmHg": 80,
        "bp.office2.targetOrganDamageOrCvd": False,
        "bp.office3.systolicMmHg": 125,
        "bp.office3.diastolicMmHg": 80,
    }


def assert_runtime_semantics() -> None:
    assert evaluate_predicate(
        {"any": [{"field": "missing_a", "op": "eq", "value": True}, {"field": "known", "op": "eq", "value": True}]},
        {"known": True},
    ) is True
    assert evaluate_predicate(
        {"all": [{"field": "missing_a", "op": "eq", "value": True}, {"field": "known", "op": "eq", "value": False}]},
        {"known": True},
    ) is False
    assert_missing(
        {"all": [{"field": "missing_a", "op": "eq", "value": True}, {"field": "missing_b", "op": "eq", "value": True}]},
        {},
        ["missing_a", "missing_b"],
    )
    missing = run(BUNDLE, "bp_diagnosis", {})
    assert missing["status"] == "needs_data"
    assert missing["missingData"] == ["bp.office1.systolicMmHg", "bp.office1.diastolicMmHg", "bp.office1.targetOrganDamageOrCvd"]
    assert missing["sourceRefs"]


def assert_validator_guards_graph() -> None:
    with tempfile.TemporaryDirectory(prefix="cdss-validator-") as temp_dir:
        duplicate_branch = json.loads(BUNDLE.read_text(encoding="utf-8"))
        tree = duplicate_branch["trees"][0]
        condition = next(node for node in tree["nodes"] if node["type"] == "condition")
        true_edge = next(edge for edge in tree["edges"] if edge["from"] == condition["id"] and edge["when"] == "true")
        false_edge = next(edge for edge in tree["edges"] if edge["from"] == condition["id"] and edge["when"] == "false")
        extra_true = copy.deepcopy(true_edge)
        extra_true["to"] = false_edge["to"]
        tree["edges"].append(extra_true)
        duplicate_path = Path(temp_dir) / "duplicate-branch.json"
        duplicate_path.write_text(json.dumps(duplicate_branch), encoding="utf-8")
        try:
            validate_bundle(duplicate_path)
        except ValueError as error:
            assert "one true and one false" in str(error), error
        else:
            raise AssertionError("validator accepted duplicate condition branch")

        skip_bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
        skip_condition = next(node for node in skip_bundle["trees"][0]["nodes"] if node["type"] == "condition")
        skip_condition["onMissingData"] = "skip"
        skip_path = Path(temp_dir) / "skip-missing-data.json"
        skip_path.write_text(json.dumps(skip_bundle), encoding="utf-8")
        try:
            validate_bundle(skip_path)
        except ValueError as error:
            assert "fail-closed" in str(error), error
        else:
            raise AssertionError("validator accepted skip-on-missing-data policy")

        cycle_bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
        optimized = next(tree for tree in cycle_bundle["trees"] if tree["id"] == "optimized_hypertension_treatment")
        link_node = next(node for node in optimized["nodes"] if node["type"] == "link")
        link_node["data"]["targetTreeId"] = optimized["id"]
        optimized["linksTo"] = [optimized["id"]]
        cycle_path = Path(temp_dir) / "cycle.json"
        cycle_path.write_text(json.dumps(cycle_bundle), encoding="utf-8")
        try:
            validate_bundle(cycle_path)
        except ValueError as error:
            assert "global tree-link cycle" in str(error), error
        else:
            raise AssertionError("validator accepted a global LINK cycle")


def assert_image_target_flows() -> None:
    tree5 = next(tree for tree in json.loads(BUNDLE.read_text(encoding="utf-8"))["trees"] if tree["id"] == "uncontrolled_resistant_hypertension")
    assert len(tree5["nodes"]) == 22
    tree5_titles = {node["display"]["title"] for node in tree5["nodes"]}
    assert "Safety & exclusion screen" in tree5_titles
    assert "Any exclusion criteria present?" in tree5_titles
    assert "Eligible for baxdrostat" in tree5_titles

    crisis = base_diagnosis()
    crisis.update({"bp.office1.systolicMmHg": 180, "bp.office1.diastolicMmHg": 80, "bp.office1.targetOrganDamageOrCvd": True})
    crisis_result = run(BUNDLE, "bp_diagnosis", crisis)
    assert crisis_result["context"]["bp.category"] == "hypertensive_crisis"

    normal_result = run(BUNDLE, "bp_diagnosis", base_diagnosis())
    assert normal_result["context"]["bp.category"] == "normal"

    home = base_diagnosis()
    home.update({"bp.measurementMethod": "home", "bp.home.systolicMmHg": 130, "bp.home.diastolicMmHg": 80})
    home_result = run(BUNDLE, "bp_diagnosis", home)
    assert home_result["context"]["bp.category"] == "white_coat_hypertension"

    second = base_diagnosis()
    second.update({"bp.office2.systolicMmHg": 150, "bp.office2.diastolicMmHg": 95, "bp.office2.targetOrganDamageOrCvd": True})
    second_result = run(BUNDLE, "bp_diagnosis", second)
    assert second_result["context"]["bp.category"] == "hypertension"

    risk_medium = run(BUNDLE, "hypertension_risk_stratification", {"bp.category": "grade2", "bp.systolicMmHg": 160, "bp.diastolicMmHg": 100, "risk.factorCount": 0, "risk.highRiskComorbidity": False})
    assert risk_medium["resultCode"] == "risk_medium"
    risk_high = run(BUNDLE, "hypertension_risk_stratification", {"bp.category": "grade2", "bp.systolicMmHg": 160, "bp.diastolicMmHg": 100, "risk.factorCount": 1, "risk.highRiskComorbidity": False})
    assert risk_high["resultCode"] == "risk_high"

    threshold = run(BUNDLE, "bp_thresholds_targets", {"bp.category": "high_normal", "risk.class": "high", "treatment.hasHighRiskComorbidity": True})
    assert threshold["context"]["treatment.targetSystolicMmHg"] == 130

    initial_combo = run(BUNDLE, "optimized_hypertension_treatment", {"patient.ageYears": 55, "bp.assessmentOfficeSystolicMmHg": 150, "bp.assessmentOfficeDiastolicMmHg": 95, "bp.category": "grade1", "treatment.hasHighRiskComorbidity": False, "treatment.mandatoryIndication": False})
    assert initial_combo["outcomeCode"] == "initial_combination_followup"

    single_pill = run(BUNDLE, "optimized_hypertension_treatment", {"patient.ageYears": 55, "bp.assessmentOfficeSystolicMmHg": 135, "bp.assessmentOfficeDiastolicMmHg": 82, "bp.category": "high_normal", "treatment.hasHighRiskComorbidity": False, "treatment.mandatoryIndication": False})
    assert single_pill["outcomeCode"] == "optimized_single_pill_followup"

    excluded = run(BUNDLE, "uncontrolled_resistant_hypertension", {
        "bp.officeAverageSystolicMmHg": 150,
        "bp.officeReadingCount": 2,
        "medication.regimenStableWeeks": 4,
        "medication.agentCount": 3,
        "medication.includesDiuretic": True,
        "resistant.egfrMlMin": 20,
        "resistant.potassiumMmolL": 4.2,
        "resistant.sodiumMmolL": 140,
        "pregnancy.status": "not_pregnant",
        "resistant.severeLiverDisease": False,
    })
    assert excluded["context"]["resistant.treatmentStatus"] == "excluded"
    assert excluded["context"]["resistant.drugRecommendation"] == "address_exclusion_and_retry"

    missing_safety = run(BUNDLE, "uncontrolled_resistant_hypertension", {
        "bp.officeAverageSystolicMmHg": 150,
        "bp.officeReadingCount": 2,
        "medication.regimenStableWeeks": 4,
        "medication.agentCount": 3,
        "medication.includesDiuretic": True,
    })
    assert missing_safety["status"] == "completed"
    assert missing_safety["resultCode"] == "resistant_safety_data_required"
    assert missing_safety["context"]["resistant.treatmentStatus"] == "not_started"

    resistant_context = {
        "patient.ageYears": 55,
        "bp.assessmentOfficeSystolicMmHg": 150,
        "bp.assessmentOfficeDiastolicMmHg": 95,
        "bp.category": "grade2",
        "treatment.hasHighRiskComorbidity": True,
        "treatment.mandatoryIndication": False,
        "medication.agentCount": 3,
        "medication.uncontrolledDespiteTripleTherapy": True,
        "bp.officeAverageSystolicMmHg": 150,
        "bp.officeReadingCount": 2,
        "medication.regimenStableWeeks": 4,
        "medication.includesDiuretic": True,
        "resistant.egfrMlMin": 60,
        "resistant.potassiumMmolL": 4.2,
        "resistant.sodiumMmolL": 140,
        "pregnancy.status": "not_pregnant",
        "resistant.severeLiverDisease": False,
        "resistant.systolicDropAt12WeeksMmHg": 9.0,
    }
    resistant = run(BUNDLE, "optimized_hypertension_treatment", resistant_context)
    assert "uncontrolled_resistant_hypertension" in resistant["linksVisited"]
    assert resistant["outcomeCode"] == "resistant_target_met"
    assert resistant["resultCode"] == "resistant_continue_therapy"

    two_drug = dict(resistant_context)
    two_drug["medication.agentCount"] = 2
    two_drug_result = run(BUNDLE, "uncontrolled_resistant_hypertension", two_drug)
    assert two_drug_result["context"]["resistant.classification"] == "uncontrolled_two_drug"

    no_diuretic = dict(resistant_context)
    no_diuretic["medication.includesDiuretic"] = False
    no_diuretic_result = run(BUNDLE, "uncontrolled_resistant_hypertension", no_diuretic)
    assert no_diuretic_result["outcomeCode"] == "add_diuretic_reclassify"

    invalid_agent_count = dict(resistant_context)
    invalid_agent_count["medication.agentCount"] = 1
    invalid_agent_count_result = run(BUNDLE, "uncontrolled_resistant_hypertension", invalid_agent_count)
    assert invalid_agent_count_result["resultCode"] == "resistant_agent_count_review_required"


def main() -> None:
    assert_runtime_semantics()
    assert_validator_guards_graph()
    assert_image_target_flows()
    print("engine smoke tests: ok")


if __name__ == "__main__":
    main()
