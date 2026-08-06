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
from decision_trees.runtime.decision_tree_engine import MissingData, evaluate_predicate, run, run_clinical_flow
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
    assert len(tree5["nodes"]) == 12
    tree5_titles = {node["display"]["title"] for node in tree5["nodes"]}
    assert "Safety & exclusion screen" not in tree5_titles
    assert "Any exclusion criteria present?" not in tree5_titles
    assert "Eligible for baxdrostat" not in tree5_titles
    assert tree5["inputVariables"] == [
        "bp.officeAverageSystolicMmHg",
        "bp.officeReadingCount",
        "medication.regimenStableWeeks",
        "medication.agentCount",
        "medication.includesDiuretic",
    ]

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
    assert threshold["context"]["treatment.targetDiastolicMmHg"] == 80
    assert threshold["context"]["treatment.targetProfile"] == "high_risk"

    initial_combo = run(BUNDLE, "optimized_hypertension_treatment", {"patient.ageYears": 55, "bp.assessmentOfficeSystolicMmHg": 150, "bp.assessmentOfficeDiastolicMmHg": 95, "bp.category": "grade1", "treatment.hasHighRiskComorbidity": False, "treatment.mandatoryIndication": False})
    assert initial_combo["outcomeCode"] == "initial_combination_followup"

    single_pill = run(BUNDLE, "optimized_hypertension_treatment", {"patient.ageYears": 55, "bp.assessmentOfficeSystolicMmHg": 135, "bp.assessmentOfficeDiastolicMmHg": 82, "bp.category": "high_normal", "treatment.hasHighRiskComorbidity": False, "treatment.mandatoryIndication": False})
    assert single_pill["outcomeCode"] == "optimized_single_pill_followup"

    uncontrolled = run(BUNDLE, "uncontrolled_resistant_hypertension", {
        "bp.officeAverageSystolicMmHg": 150,
        "bp.officeReadingCount": 2,
        "medication.regimenStableWeeks": 4,
        "medication.agentCount": 2,
        "medication.includesDiuretic": False,
    })
    assert uncontrolled["context"]["resistant.classification"] == "uncontrolled_two_drug"
    assert uncontrolled["resultCode"] == "uncontrolled_htn_arm"

    missing_classification_data = run(BUNDLE, "uncontrolled_resistant_hypertension", {
        "bp.officeAverageSystolicMmHg": 150,
        "bp.officeReadingCount": 2,
        "medication.regimenStableWeeks": 4,
    })
    assert missing_classification_data["status"] == "needs_data"
    assert missing_classification_data["missingData"] == ["medication.agentCount"]

    resistant_context = {
        "patient.ageYears": 55,
        "bp.assessmentOfficeSystolicMmHg": 150,
        "bp.assessmentOfficeDiastolicMmHg": 95,
        "bp.category": "grade2",
        "treatment.hasHighRiskComorbidity": True,
        "treatment.mandatoryIndication": False,
        "medication.agentCount": 3,
        "treatment.targetSystolicMmHg": 130,
        "treatment.targetDiastolicMmHg": 80,
        "treatment.targetProfile": "high_risk",
        "bp.officeAverageSystolicMmHg": 150,
        "bp.officeReadingCount": 2,
        "medication.regimenStableWeeks": 4,
        "medication.includesDiuretic": True,
    }
    resistant = run(BUNDLE, "optimized_hypertension_treatment", resistant_context)
    assert "uncontrolled_resistant_hypertension" in resistant["linksVisited"]
    assert resistant["outcomeCode"] == "resistant_three_or_more_with_diuretic_classified"
    assert resistant["resultCode"] == "resistant_htn_arm"

    controlled_context = dict(resistant_context)
    controlled_context.update({
        "bp.assessmentOfficeSystolicMmHg": 129,
        "bp.assessmentOfficeDiastolicMmHg": 79,
    })
    controlled = run(BUNDLE, "optimized_hypertension_treatment", controlled_context)
    assert controlled["outcomeCode"] == "triple_combination_followup"
    assert controlled["resultCode"] == "triple_combination_followup"

    target_boundary = dict(resistant_context)
    target_boundary.update({
        "bp.assessmentOfficeSystolicMmHg": 140,
        "bp.assessmentOfficeDiastolicMmHg": 80,
        "treatment.targetSystolicMmHg": 140,
        "treatment.targetDiastolicMmHg": 80,
        "treatment.targetProfile": "no_comorbidity",
    })
    boundary_result = run(BUNDLE, "optimized_hypertension_treatment", target_boundary)
    assert boundary_result["terminalTreeId"] == "uncontrolled_resistant_hypertension"
    assert boundary_result["resultCode"] == "resistant_htn_arm"

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

    flow_context = {
        "bp.category": "grade1",
        "risk.class": "low",
        "treatment.hasHighRiskComorbidity": False,
        "patient.ageYears": 55,
        "bp.assessmentOfficeSystolicMmHg": 129,
        "bp.assessmentOfficeDiastolicMmHg": 79,
        "treatment.mandatoryIndication": False,
        "medication.agentCount": 3,
        "bp.officeAverageSystolicMmHg": 150,
        "bp.officeReadingCount": 2,
        "medication.regimenStableWeeks": 4,
        "medication.includesDiuretic": True,
    }
    controlled_flow = run_clinical_flow(BUNDLE, flow_context)
    assert [step["treeId"] for step in controlled_flow["steps"]] == [
        "bp_thresholds_targets",
        "optimized_hypertension_treatment",
    ]
    assert controlled_flow["context"]["treatment.targetSystolicMmHg"] == 140
    assert controlled_flow["resultCode"] == "triple_combination_followup"
    assert controlled_flow["outcomeCode"] == "triple_combination_followup"

    uncontrolled_flow_context = dict(flow_context)
    uncontrolled_flow_context.update({
        "bp.assessmentOfficeSystolicMmHg": 150,
        "bp.assessmentOfficeDiastolicMmHg": 95,
    })
    uncontrolled_flow = run_clinical_flow(BUNDLE, uncontrolled_flow_context)
    assert [step["treeId"] for step in uncontrolled_flow["steps"]] == [
        "bp_thresholds_targets",
        "optimized_hypertension_treatment",
    ]
    assert uncontrolled_flow["terminalTreeId"] == "uncontrolled_resistant_hypertension"
    assert uncontrolled_flow["resultCode"] == "resistant_htn_arm"
    assert uncontrolled_flow["outcomeCode"] == "resistant_three_or_more_with_diuretic_classified"
    assert uncontrolled_flow["linksVisited"] == ["uncontrolled_resistant_hypertension"]


def main() -> None:
    assert_runtime_semantics()
    assert_validator_guards_graph()
    assert_image_target_flows()
    print("engine smoke tests: ok")


if __name__ == "__main__":
    main()
