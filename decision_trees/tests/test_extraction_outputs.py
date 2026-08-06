#!/usr/bin/env python3
"""Branch-matrix and contract tests for the five extracted tree outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decision_trees.config.paths import BUNDLE_PATH, PROJECT_ROOT
from decision_trees.runtime.decision_tree_engine import run
from decision_trees.runtime.validate_decision_tree_bundle import validate_bundle


TREE_IDS = {
    "bp_diagnosis",
    "bp_thresholds_targets",
    "optimized_hypertension_treatment",
    "hypertension_risk_stratification",
    "uncontrolled_resistant_hypertension",
}
RESULTS_DIR = PROJECT_ROOT / "results"


def assert_result(tree_id: str, case_name: str, variables: dict[str, Any], result_code: str, outcome_code: str) -> dict[str, Any]:
    result = run(BUNDLE_PATH, tree_id, variables)
    assert result["status"] == "completed", (tree_id, case_name, result)
    assert result["resultCode"] == result_code, (tree_id, case_name, result)
    assert result["outcomeCode"] == outcome_code, (tree_id, case_name, result)
    assert result["trace"], (tree_id, case_name, "empty trace")
    assert result["sourceRefs"], (tree_id, case_name, "empty sourceRefs")
    assert result["entryTreeId"] == tree_id
    assert result["terminalTreeId"] == result["treeId"]
    return result


def diagnosis_base() -> dict[str, Any]:
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


def resistant_base() -> dict[str, Any]:
    return {
        "bp.officeAverageSystolicMmHg": 150,
        "bp.officeReadingCount": 2,
        "medication.regimenStableWeeks": 4,
        "medication.agentCount": 3,
        "medication.includesDiuretic": True,
    }


def test_result_files_contract() -> None:
    bundle_summary = validate_bundle(BUNDLE_PATH)
    assert bundle_summary == {"trees": 5, "variables": 55, "nodes": 82, "edges": 80, "links": 1}
    result_paths = sorted(RESULTS_DIR.glob("*.json"))
    assert {path.stem for path in result_paths} == TREE_IDS

    for path in result_paths:
        wrapper = json.loads(path.read_text(encoding="utf-8"))
        tree_id = path.stem
        assert wrapper["treeId"] == tree_id
        result = wrapper["result"]
        assert result["entryTreeId"] == tree_id
        assert result["terminalTreeId"] == result["treeId"]
        assert result["status"] == "completed"
        assert isinstance(result.get("resultCode"), str) and result["resultCode"]
        assert isinstance(result.get("outcomeCode"), str) and result["outcomeCode"]
        assert result["trace"]
        assert result["sourceRefs"]
        assert result["validation"] == bundle_summary


def test_branch_matrix() -> None:
    base = diagnosis_base()
    diagnosis_cases = [
        ("crisis", {**base, "bp.office1.systolicMmHg": 180, "bp.office1.targetOrganDamageOrCvd": True}, "hypertensive_crisis", "hypertensive_crisis_detected"),
        ("second_measurement_hypertension", {**base, "bp.office2.systolicMmHg": 150, "bp.office2.diastolicMmHg": 95, "bp.office2.targetOrganDamageOrCvd": True}, "hypertension", "hypertension_detected"),
        ("office_normal", base, "normal_bp", "normal_bp"),
        ("office_high_normal", {**base, "bp.office3.systolicMmHg": 135}, "high_normal_bp", "high_normal_bp"),
        ("office_hypertension", {**base, "bp.office3.systolicMmHg": 140}, "hypertension", "hypertension_detected"),
        ("home_white_coat", {**base, "bp.measurementMethod": "home", "bp.home.systolicMmHg": 134, "bp.home.diastolicMmHg": 84}, "white_coat_hypertension", "white_coat_hypertension"),
        ("home_masked", {**base, "bp.measurementMethod": "home", "bp.home.systolicMmHg": 135, "bp.home.diastolicMmHg": 85}, "masked_hypertension", "masked_hypertension"),
        ("abpm_white_coat", {**base, "bp.measurementMethod": "abpm_24h", "bp.abpm.daytime.systolicMmHg": 134, "bp.abpm.daytime.diastolicMmHg": 84, "bp.abpm.average24h.systolicMmHg": 129, "bp.abpm.average24h.diastolicMmHg": 79}, "white_coat_hypertension", "white_coat_hypertension"),
        ("abpm_masked", {**base, "bp.measurementMethod": "abpm_24h", "bp.abpm.daytime.systolicMmHg": 135, "bp.abpm.daytime.diastolicMmHg": 85, "bp.abpm.average24h.systolicMmHg": 130, "bp.abpm.average24h.diastolicMmHg": 80}, "masked_hypertension", "masked_hypertension"),
    ]
    for name, variables, result_code, outcome_code in diagnosis_cases:
        assert_result("bp_diagnosis", name, variables, result_code, outcome_code)

    threshold_cases = [
        ("high_normal_lifestyle", {"bp.category": "high_normal", "risk.class": "low", "treatment.hasHighRiskComorbidity": False}, "high_normal_lifestyle", "high_normal_lifestyle_followup"),
        ("high_normal_comorbidity", {"bp.category": "high_normal", "risk.class": "low", "treatment.hasHighRiskComorbidity": True}, "high_normal_comorbidity", "high_normal_comorbidity_treatment_started"),
        ("high_normal_high_risk", {"bp.category": "high_normal", "risk.class": "high", "treatment.hasHighRiskComorbidity": False}, "high_normal_high_risk_treatment", "high_normal_high_risk_treatment_started"),
        ("hypertension_standard", {"bp.category": "grade1", "risk.class": "low", "treatment.hasHighRiskComorbidity": False}, "hypertension_medication_start", "hypertension_treatment_started"),
        ("hypertension_comorbidity", {"bp.category": "grade1", "risk.class": "low", "treatment.hasHighRiskComorbidity": True}, "hypertension_comorbidity_medication", "hypertension_comorbidity_treatment_started"),
        ("hypertension_high_risk", {"bp.category": "grade1", "risk.class": "high", "treatment.hasHighRiskComorbidity": False}, "hypertension_high_risk_medication", "hypertension_high_risk_treatment_started"),
    ]
    for name, variables, result_code, outcome_code in threshold_cases:
        assert_result("bp_thresholds_targets", name, variables, result_code, outcome_code)

    target_cases = [
        ("high_risk", {"bp.category": "grade1", "risk.class": "high", "treatment.hasHighRiskComorbidity": False}, "hypertension_high_risk_medication", "hypertension_high_risk_treatment_started", 130, 80, "high_risk"),
        ("comorbidity", {"bp.category": "grade1", "risk.class": "low", "treatment.hasHighRiskComorbidity": True}, "hypertension_comorbidity_medication", "hypertension_comorbidity_treatment_started", 130, 80, "comorbidity"),
        ("no_comorbidity", {"bp.category": "grade1", "risk.class": "low", "treatment.hasHighRiskComorbidity": False}, "hypertension_medication_start", "hypertension_treatment_started", 140, 80, "no_comorbidity"),
    ]
    for name, variables, result_code, outcome_code, target_systolic, target_diastolic, profile in target_cases:
        target_result = assert_result("bp_thresholds_targets", name, variables, result_code, outcome_code)
        assert target_result["context"]["treatment.targetSystolicMmHg"] == target_systolic
        assert target_result["context"]["treatment.targetDiastolicMmHg"] == target_diastolic
        assert target_result["context"]["treatment.targetProfile"] == profile

    optimized_common = {
        "patient.ageYears": 55,
        "bp.assessmentOfficeSystolicMmHg": 150,
        "bp.assessmentOfficeDiastolicMmHg": 95,
        "bp.category": "grade1",
        "treatment.hasHighRiskComorbidity": True,
        "treatment.mandatoryIndication": False,
        "medication.agentCount": 3,
        "treatment.targetSystolicMmHg": 130,
        "treatment.targetDiastolicMmHg": 80,
        "treatment.targetProfile": "high_risk",
    }
    optimized_cases = [
        ("single_pill", {**optimized_common, "bp.category": "high_normal", "treatment.hasHighRiskComorbidity": False}, "optimized_single_pill_strategy", "optimized_single_pill_followup"),
        ("mandatory", {**optimized_common, "treatment.mandatoryIndication": True}, "mandatory_indication_treatment", "mandatory_indication_treatment_started"),
        ("combination_without_agent_count", {key: value for key, value in optimized_common.items() if key != "medication.agentCount"}, "initial_combination_followup", "initial_combination_followup"),
        ("combination_one_agent", {**optimized_common, "medication.agentCount": 1}, "initial_combination_followup", "initial_combination_followup"),
        ("triple_followup", {**optimized_common, "bp.assessmentOfficeSystolicMmHg": 129, "bp.assessmentOfficeDiastolicMmHg": 79}, "triple_combination_followup", "triple_combination_followup"),
        ("triple_uncontrolled_links", {**optimized_common, **resistant_base()}, "resistant_htn_arm", "resistant_three_or_more_with_diuretic_classified"),
        ("entry_review", {**optimized_common, "patient.ageYears": 18, "bp.assessmentOfficeSystolicMmHg": 129, "bp.assessmentOfficeDiastolicMmHg": 84, "bp.category": "normal", "treatment.hasHighRiskComorbidity": False}, "optimized_treatment_review_required", "optimized_treatment_review_required"),
    ]
    for name, variables, result_code, outcome_code in optimized_cases:
        assert_result("optimized_hypertension_treatment", name, variables, result_code, outcome_code)

    risk_cases = [
        ("high_comorbidity", {"bp.category": "normal", "bp.systolicMmHg": 120, "bp.diastolicMmHg": 70, "risk.factorCount": 0, "risk.highRiskComorbidity": True}, "risk_high", "risk_high"),
        ("grade2_high_band", {"bp.category": "grade2", "bp.systolicMmHg": 180, "bp.diastolicMmHg": 110, "risk.factorCount": 0, "risk.highRiskComorbidity": False}, "risk_high", "risk_high"),
        ("grade2_with_factor", {"bp.category": "grade2", "bp.systolicMmHg": 160, "bp.diastolicMmHg": 100, "risk.factorCount": 1, "risk.highRiskComorbidity": False}, "risk_high", "risk_high"),
        ("grade2_without_factor", {"bp.category": "grade2", "bp.systolicMmHg": 160, "bp.diastolicMmHg": 100, "risk.factorCount": 0, "risk.highRiskComorbidity": False}, "risk_medium", "risk_medium"),
        ("grade1_high", {"bp.category": "grade1", "bp.systolicMmHg": 150, "bp.diastolicMmHg": 95, "risk.factorCount": 3, "risk.highRiskComorbidity": False}, "risk_high", "risk_high"),
        ("grade1_medium", {"bp.category": "grade1", "bp.systolicMmHg": 150, "bp.diastolicMmHg": 95, "risk.factorCount": 1, "risk.highRiskComorbidity": False}, "risk_medium", "risk_medium"),
        ("grade1_low", {"bp.category": "grade1", "bp.systolicMmHg": 150, "bp.diastolicMmHg": 95, "risk.factorCount": 0, "risk.highRiskComorbidity": False}, "risk_low", "risk_low"),
        ("high_normal_medium", {"bp.category": "high_normal", "bp.systolicMmHg": 135, "bp.diastolicMmHg": 85, "risk.factorCount": 3, "risk.highRiskComorbidity": False}, "risk_medium", "risk_medium"),
        ("high_normal_low", {"bp.category": "high_normal", "bp.systolicMmHg": 135, "bp.diastolicMmHg": 85, "risk.factorCount": 0, "risk.highRiskComorbidity": False}, "risk_low", "risk_low"),
        ("normal_low", {"bp.category": "normal", "bp.systolicMmHg": 120, "bp.diastolicMmHg": 70, "risk.factorCount": 0, "risk.highRiskComorbidity": False}, "risk_low", "risk_low"),
    ]
    for name, variables, result_code, outcome_code in risk_cases:
        assert_result("hypertension_risk_stratification", name, variables, result_code, outcome_code)

    resistant_cases = [
        ("out_of_range", {"bp.officeAverageSystolicMmHg": 170, "bp.officeReadingCount": 2}, "resistant_out_of_range", "resistant_out_of_range_manage_first"),
        ("defer", {"bp.officeAverageSystolicMmHg": 150, "bp.officeReadingCount": 2, "medication.regimenStableWeeks": 3}, "resistant_defer", "resistant_defer_reassess"),
        ("two_drug", {**resistant_base(), "medication.agentCount": 2}, "uncontrolled_htn_arm", "uncontrolled_two_drug_classified"),
        ("three_without_diuretic", {**resistant_base(), "medication.includesDiuretic": False}, "add_diuretic", "add_diuretic_reclassify"),
        ("invalid_agent_count", {**resistant_base(), "medication.agentCount": 1, "medication.includesDiuretic": False}, "resistant_agent_count_review_required", "resistant_agent_count_review_required"),
    ]
    for name, variables, result_code, outcome_code in resistant_cases:
        assert_result("uncontrolled_resistant_hypertension", name, variables, result_code, outcome_code)

    linked = {**optimized_common, **resistant_base()}
    linked_result = assert_result("optimized_hypertension_treatment", "link_to_tree_5", linked, "resistant_htn_arm", "resistant_three_or_more_with_diuretic_classified")
    assert linked_result["terminalTreeId"] == "uncontrolled_resistant_hypertension"
    assert linked_result["linksVisited"] == ["uncontrolled_resistant_hypertension"]


def main() -> None:
    test_result_files_contract()
    test_branch_matrix()
    print("extraction output tests: ok")


if __name__ == "__main__":
    main()
