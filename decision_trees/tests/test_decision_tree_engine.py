#!/usr/bin/env python3
"""Smoke tests for the currently active two-stage hypertension flow."""

from __future__ import annotations

import json

from decision_trees.config.paths import BUNDLE_PATH
from decision_trees.runtime.decision_tree_engine import (
    derive_bp_control_variables,
    derive_medication_variables,
    derive_patient_problem_variables,
    derive_patient_measurement_variables,
    run,
    run_clinical_flow,
)


def diagnosis_input(codes: str = "I25.1, E11.9") -> dict:
    return {
        "bp.office1.systolicMmHg": 130,
        "bp.office1.diastolicMmHg": 80,
        "bp.office2.systolicMmHg": 130,
        "bp.office2.diastolicMmHg": 80,
        "bp.office3.systolicMmHg": 125,
        "bp.office3.diastolicMmHg": 80,
        "patient.diagnosisCodes": codes,
    }


def test_icd10_and_snomed_flags_are_derived() -> None:
    derived = derive_patient_problem_variables({"patient.diagnosisCodes": "I25.1; E11.9; N18.3; 25488008"})
    assert derived["comorbidity.coronaryArteryDisease"] is True
    assert derived["comorbidity.diabetes"] is True
    assert derived["comorbidity.ckd"] is True
    assert derived["comorbidity.leftVentricularHypertrophy"] is True
    assert derived["comorbidity.targetOrganDamageOrCvd"] is True
    assert derived["treatment.hasHighRiskComorbidity"] is True


def test_tree_one_uses_derived_disease_code_flag() -> None:
    result = run(BUNDLE_PATH, "bp_diagnosis", diagnosis_input())
    assert result["status"] == "completed"
    assert result["resultCode"] == "hypertensive_crisis"
    assert result["context"]["comorbidity.coronaryArteryDisease"] is True
    assert result["context"]["treatment.hasHighRiskComorbidity"] is True


def test_tree_one_detects_crisis_from_patient_code_context() -> None:
    values = diagnosis_input("")
    values.update({
        "bp.office1.systolicMmHg": 180,
        "bp.office1.diastolicMmHg": 80,
    })
    result = run(BUNDLE_PATH, "bp_diagnosis", values)
    assert result["resultCode"] == "hypertensive_crisis"


def test_tree_two_uses_derived_high_risk_comorbidity() -> None:
    result = run(BUNDLE_PATH, "bp_thresholds_targets", {
        "bp.category": "hypertension",
        "risk.class": "low",
        "encounter.number": 2,
        "patient.diagnosisCodes": "I50.9",
    })
    assert result["status"] == "completed"
    assert result["resultCode"] == "hypertension_comorbidity_medication"
    assert result["context"]["treatment.hasHighRiskComorbidity"] is True
    assert result["context"]["treatment.targetSystolicMmHg"] == 130


def test_antihypertensive_names_are_grouped_without_counting_duplicate_classes() -> None:
    derived = derive_medication_variables({
        "medication.currentDrugNames": "Losartan, amlodipine, indapamide, spironolactone",
    })
    assert derived["medication.currentDrugClassCodes"] == "arb,ccb,diuretic,mra"
    assert derived["medication.currentDrugClassList"] == ["arb", "ccb", "diuretic", "mra"]
    assert derived["medication.currentDrugClassCount"] == 4
    assert derived["medication.currentIncludesDiuretic"] is True
    assert derived["medication.currentUnmappedDrugNames"] == ""
    assert derived["medication.currentHasUnmappedDrug"] is False


def test_bp_control_is_derived_from_current_encounter_and_tree_two_target() -> None:
    derived = derive_bp_control_variables({
        "bp.latest.systolicMmHg": 129,
        "bp.latest.diastolicMmHg": 79,
        "treatment.targetSystolicMmHg": 130,
        "treatment.targetDiastolicMmHg": 80,
    })
    assert derived == {
        "bp.controlledAfterTwoDrugs": True,
        "bp.controlledAfterThreeDrugs": True,
        "bp.controlledAfterFourDrugs": True,
    }


def test_antihypertensive_catalog_supports_vietnamese_table_groups() -> None:
    bundle = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    variable = next(item for item in bundle["variables"] if item["id"] == "medication.drugClass")
    assert variable["allowedValues"] == ["acei", "arb", "ccb", "beta_blocker", "diuretic", "mra", "other"]


def test_expected_patient_measurements_are_derived() -> None:
    context = {
        "asOf": "2026-08-11",
        "patient.birthDate": "1960-08-12",
        "patient.sex": "male",
        "vitals.heartRate": 81,
        "patient.heightM": 1.7,
        "patient.weightKg": 72.25,
        "lab.eGfr": 59,
        "patient.diagnosisCodes": "E11.9, I25.1",
        "risk.lipidAbnormality": True,
        "risk.familyHistoryPrematureCvd": False,
        "risk.currentSmoker": True,
        "risk.socialEnvironmentalRisk": False,
    }
    context.update(derive_patient_problem_variables(context))
    derived = derive_patient_measurement_variables(context)

    assert derived["patient.ageYears"] == 65
    assert abs(derived["patient.bmi"] - 25) < 1e-9
    assert derived["risk.ageOver65"] is False
    assert derived["risk.maleSex"] is True
    assert derived["risk.heartRateOver80"] is True
    assert derived["risk.overweight"] is True
    assert derived["risk.ckdStageAtLeast3"] is True
    assert derived["risk.diabetes"] is True
    assert derived["risk.cardiovascularDisease"] is True
    assert derived["risk.targetOrganDamage"] is True
    assert derived["comorbidity.targetOrganDamageOrCvd"] is True
    assert derived["risk.highRiskComorbidity"] is True
    assert derived["treatment.hasHighRiskComorbidity"] is True
    assert derived["risk.factorCount"] == 6


def test_expected_derived_variables_remain_missing_without_sources() -> None:
    assert derive_patient_problem_variables({}) == {}
    assert derive_patient_measurement_variables({}) == {}


def test_latest_bp_uses_latest_complete_office_pair() -> None:
    derived = derive_patient_measurement_variables({
        "bp.office1.systolicMmHg": 150,
        "bp.office1.diastolicMmHg": 95,
        "bp.office2.systolicMmHg": 140,
        "bp.office2.diastolicMmHg": 90,
        "bp.office3.systolicMmHg": 130,
        "bp.office3.diastolicMmHg": 80,
    })
    assert derived["bp.latest.systolicMmHg"] == 130
    assert derived["bp.latest.diastolicMmHg"] == 80

    fallback = derive_patient_measurement_variables({
        "bp.office1.systolicMmHg": 150,
        "bp.office1.diastolicMmHg": 95,
        "bp.office2.systolicMmHg": 140,
        "bp.office2.diastolicMmHg": 90,
    })
    assert fallback["bp.latest.systolicMmHg"] == 140
    assert fallback["bp.latest.diastolicMmHg"] == 90


def risk_tree_input(**overrides: object) -> dict:
    values = {
        "bp.office3.systolicMmHg": 150,
        "bp.office3.diastolicMmHg": 95,
        "patient.diagnosisCodes": "",
        "risk.ageOver65": False,
        "risk.maleSex": False,
        "risk.heartRateOver80": False,
        "risk.overweight": False,
        "risk.lipidAbnormality": False,
        "risk.familyHistoryPrematureCvd": False,
        "risk.currentSmoker": False,
        "risk.socialEnvironmentalRisk": False,
    }
    values.update(overrides)
    return values


def test_tree_four_classifies_grade_one_by_risk_factor_count() -> None:
    low = run(BUNDLE_PATH, "hypertension_risk_stratification", risk_tree_input())
    medium = run(BUNDLE_PATH, "hypertension_risk_stratification", risk_tree_input(**{
        "risk.maleSex": True,
        "risk.currentSmoker": True,
    }))
    high = run(BUNDLE_PATH, "hypertension_risk_stratification", risk_tree_input(**{
        "risk.ageOver65": True,
        "risk.maleSex": True,
        "risk.heartRateOver80": True,
    }))
    assert low["resultCode"] == "risk_low"
    assert medium["resultCode"] == "risk_medium"
    assert high["resultCode"] == "risk_high"
    assert low["context"]["risk.factorCount"] == 0
    assert medium["context"]["risk.factorCount"] == 2
    assert high["context"]["risk.factorCount"] == 3


def test_tree_four_classifies_grade_two_lower_band_without_risk_factors_as_medium() -> None:
    result = run(BUNDLE_PATH, "hypertension_risk_stratification", risk_tree_input(
        **{
            "bp.office3.systolicMmHg": 160,
            "bp.office3.diastolicMmHg": 100,
        },
    ))
    assert result["status"] == "completed"
    assert result["resultCode"] == "risk_medium"


def test_tree_four_classifies_high_risk_icd10_as_high_without_manual_boolean() -> None:
    result = run(BUNDLE_PATH, "hypertension_risk_stratification", {
        "patient.diagnosisCodes": "I25.1",
    })
    assert result["status"] == "completed"
    assert result["resultCode"] == "risk_high"
    assert result["context"]["risk.highRiskComorbidity"] is True


def test_tree_five_classifies_two_drug_regimen_as_uncontrolled() -> None:
    result = run(BUNDLE_PATH, "uncontrolled_resistant_hypertension", {
        "bp.office3.systolicMmHg": 150,
        "bp.office3.diastolicMmHg": 95,
        "medication.regimenStableWeeks": 4,
        "medication.currentDrugNames": "Losartan, amlodipine",
    })
    assert result["status"] == "completed"
    assert result["resultCode"] == "uncontrolled_htn_arm"
    assert result["context"]["medication.currentDrugClassCount"] == 2


def test_tree_five_classifies_three_drugs_with_diuretic_as_resistant() -> None:
    result = run(BUNDLE_PATH, "uncontrolled_resistant_hypertension", {
        "bp.office3.systolicMmHg": 150,
        "bp.office3.diastolicMmHg": 95,
        "medication.regimenStableWeeks": 4,
        "medication.currentDrugNames": "Losartan, amlodipine, indapamide",
    })
    assert result["status"] == "completed"
    assert result["resultCode"] == "resistant_htn_arm"
    assert result["context"]["medication.currentDrugClassCount"] == 3
    assert result["context"]["medication.currentIncludesDiuretic"] is True


def test_tree_five_defers_when_regimen_is_not_stable() -> None:
    result = run(BUNDLE_PATH, "uncontrolled_resistant_hypertension", {
        "bp.office3.systolicMmHg": 150,
        "bp.office3.diastolicMmHg": 95,
        "medication.regimenStableWeeks": 3,
        "medication.currentDrugNames": "Losartan, amlodipine",
    })
    assert result["status"] == "completed"
    assert result["resultCode"] == "resistant_defer"


def test_tree_five_stops_when_a_drug_is_not_in_the_catalog() -> None:
    result = run(BUNDLE_PATH, "uncontrolled_resistant_hypertension", {
        "bp.office3.systolicMmHg": 150,
        "bp.office3.diastolicMmHg": 95,
        "medication.regimenStableWeeks": 4,
        "medication.currentDrugNames": "Losartan, unknown-drug",
    })
    assert result["status"] == "completed"
    assert result["resultCode"] == "resistant_drug_review_required"
    assert result["context"]["medication.currentHasUnmappedDrug"] is True


def test_tree_three_uses_previous_encounter_drug_list_and_escalates_by_control() -> None:
    result = run(BUNDLE_PATH, "optimized_hypertension_treatment", {
        "patient.birthDate": "1990-01-01",
        "asOf": "2026-08-11",
        "bp.category": "hypertension",
        "treatment.recommendation": "medication_now",
        "risk.class": "low",
        "treatment.hasHighRiskComorbidity": False,
        "encounter.number": 2,
        "patient.diagnosisCodes": "",
        "medication.previousEncounterDrugNames": "Losartan, amlodipine",
        "bp.controlledAfterTwoDrugs": False,
        "bp.controlledAfterThreeDrugs": False,
        "bp.controlledAfterFourDrugs": False,
    })
    assert result["status"] == "completed"
    assert result["resultCode"] == "followup_escalate_three_drugs"
    assert result["context"]["medication.previousEncounterDrugClassCodes"] == "arb,ccb"
    assert result["context"]["medication.previousEncounterDrugClassList"] == ["arb", "ccb"]
    assert result["context"]["medication.previousEncounterAgentCount"] == 2


def test_tree_three_new_patient_does_not_use_current_drug_count() -> None:
    result = run(BUNDLE_PATH, "optimized_hypertension_treatment", {
        "patient.birthDate": "1990-01-01",
        "asOf": "2026-08-11",
        "bp.category": "high_normal",
        "treatment.recommendation": "lifestyle_first",
        "risk.class": "low",
        "treatment.hasHighRiskComorbidity": False,
        "encounter.number": 1,
        "patient.diagnosisCodes": "",
        "medication.currentDrugNames": "Losartan, amlodipine, indapamide",
    })
    assert result["status"] == "completed"
    assert result["resultCode"] == "new_patient_lifestyle_first"
    assert result["context"]["medication.currentDrugClassCount"] == 3


def test_tree_three_encounter_condition_uses_followup_for_encounter_greater_than_one() -> None:
    result = run(BUNDLE_PATH, "optimized_hypertension_treatment", {
        "patient.birthDate": "1990-01-01",
        "asOf": "2026-08-11",
        "bp.category": "high_normal",
        "treatment.recommendation": "lifestyle_first",
        "risk.class": "low",
        "treatment.hasHighRiskComorbidity": False,
        "encounter.number": 1,
        "patient.diagnosisCodes": "",
        "medication.currentDrugNames": "Losartan, amlodipine, indapamide",
    })
    assert result["status"] == "completed"
    assert result["resultCode"] == "new_patient_lifestyle_first"
    encounter_event = next(
        event for event in result["trace"]
        if event.get("nodeId") == "optimized_encounter_type"
    )
    assert encounter_event["value"] is False


def test_edge_labels_are_conditions_without_embedded_outcomes() -> None:
    bundle = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    forbidden = ("→", "->")
    for tree in bundle["trees"]:
        for edge in tree["edges"]:
            label = edge.get("label", "")
            assert not any(token in label for token in forbidden), (tree["id"], edge)


def test_inter_tree_links_cover_the_clinical_flow() -> None:
    bundle = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    expected = {
        "bp_diagnosis": {"hypertension_risk_stratification"},
        "hypertension_risk_stratification": {"bp_thresholds_targets"},
        "bp_thresholds_targets": {"optimized_hypertension_treatment"},
        "optimized_hypertension_treatment": {"uncontrolled_resistant_hypertension"},
        "uncontrolled_resistant_hypertension": set(),
    }
    for tree in bundle["trees"]:
        links = {
            node["data"]["targetTreeId"]
            for node in tree["nodes"]
            if node["type"] == "link"
        }
        assert links == expected[tree["id"]]
        for node in tree["nodes"]:
            if node["type"] == "link" and node["data"]["targetTreeId"] != "uncontrolled_resistant_hypertension":
                assert node["data"].get("callMode") == "navigate_only"


def test_tree_three_mandatory_branch_has_five_disease_outputs() -> None:
    cases = [
        ("I25.1", "mandatory_coronary_artery_disease", "coronary_artery_disease"),
        ("I50.2", "mandatory_heart_failure_reduced_ef", "heart_failure_reduced_ef"),
        ("I63.9", "mandatory_stroke", "stroke"),
        ("N18.3", "mandatory_chronic_kidney_disease", "chronic_kidney_disease"),
        ("E11.9", "mandatory_type2_diabetes", "type2_diabetes"),
    ]
    for diagnosis_code, result_code, disease_code in cases:
        result = run(BUNDLE_PATH, "optimized_hypertension_treatment", {
            "patient.birthDate": "1990-01-01",
            "asOf": "2026-08-11",
            "bp.category": "hypertension",
            "treatment.recommendation": "medication_now",
            "risk.class": "low",
            "encounter.number": 2,
            "patient.diagnosisCodes": diagnosis_code,
            "medication.previousEncounterDrugNames": "Losartan",
        })
        assert result["status"] == "completed"
        assert result["resultCode"] == result_code
        assert result["context"]["treatment.mandatoryDisease"] == disease_code
        assert result["context"]["treatment.initialRegimen"] == "mandatory_indication"


def test_tree_three_links_four_drug_uncontrolled_case_to_tree_five() -> None:
    result = run(BUNDLE_PATH, "optimized_hypertension_treatment", {
        "patient.birthDate": "1990-01-01",
        "asOf": "2026-08-11",
        "bp.category": "hypertension",
        "treatment.recommendation": "medication_now",
        "risk.class": "low",
        "treatment.hasHighRiskComorbidity": False,
        "encounter.number": 2,
        "patient.diagnosisCodes": "",
        "medication.previousEncounterDrugNames": "Losartan, amlodipine, bisoprolol, indapamide",
        "bp.controlledAfterFourDrugs": False,
        "bp.office3.systolicMmHg": 150,
        "bp.office3.diastolicMmHg": 95,
        "medication.regimenStableWeeks": 4,
        "medication.currentDrugNames": "Losartan, amlodipine, bisoprolol, indapamide",
    })
    assert result["status"] == "completed"
    assert result["resultCode"] == "resistant_htn_arm"
    assert result["linksVisited"] == ["uncontrolled_resistant_hypertension"]


def test_full_clinical_flow_passes_tree_outputs_forward_to_tree_five() -> None:
    result = run_clinical_flow(BUNDLE_PATH, {
        "bp.office1.systolicMmHg": 130,
        "bp.office1.diastolicMmHg": 80,
        "bp.office2.systolicMmHg": 130,
        "bp.office2.diastolicMmHg": 80,
        "bp.office3.systolicMmHg": 150,
        "bp.office3.diastolicMmHg": 95,
        "patient.birthDate": "1990-01-01",
        "asOf": "2026-08-11",
        "patient.diagnosisCodes": "NO_KNOWN_CODES",
        "encounter.number": 2,
        "risk.ageOver65": False,
        "risk.maleSex": False,
        "risk.heartRateOver80": False,
        "risk.overweight": False,
        "risk.lipidAbnormality": False,
        "risk.familyHistoryPrematureCvd": False,
        "risk.currentSmoker": False,
        "risk.socialEnvironmentalRisk": False,
        "medication.previousEncounterDrugNames": "Losartan, amlodipine, bisoprolol, indapamide",
        "medication.currentDrugNames": "Losartan, amlodipine, bisoprolol, indapamide",
        "medication.regimenStableWeeks": 4,
        "bp.controlledAfterFourDrugs": False,
    }, start_tree_id="bp_diagnosis")
    assert result["status"] == "completed"
    assert result["terminalTreeId"] == "uncontrolled_resistant_hypertension"
    assert result["resultCode"] == "resistant_htn_arm"
    assert [step["treeId"] for step in result["steps"]] == [
        "bp_diagnosis",
        "hypertension_risk_stratification",
        "bp_thresholds_targets",
        "optimized_hypertension_treatment",
    ]
    assert result["sets"]["treatment.targetSystolicMmHg"] == 140
    assert result["sets"]["resistant.classification"] == "resistant_three_or_more_with_diuretic"


def test_clinical_flow_stops_at_terminal_crisis_without_following_unrelated_trees() -> None:
    result = run_clinical_flow(BUNDLE_PATH, {
        "bp.office1.systolicMmHg": 180,
        "bp.office1.diastolicMmHg": 80,
        "patient.diagnosisCodes": "",
    })
    assert result["status"] == "completed"
    assert result["resultCode"] == "hypertensive_crisis"
    assert result["terminalTreeId"] == "bp_diagnosis"
    assert [step["treeId"] for step in result["steps"]] == ["bp_diagnosis"]
    assert result["linksVisited"] == []


def test_clinical_flow_stops_at_review_end_without_following_treatment_tree() -> None:
    result = run_clinical_flow(BUNDLE_PATH, {
        "bp.category": "normal",
        "risk.class": "low",
        "treatment.hasHighRiskComorbidity": False,
        "encounter.number": 2,
        "patient.diagnosisCodes": "",
    }, start_tree_id="bp_thresholds_targets")
    assert result["status"] == "completed"
    assert result["resultCode"] == "threshold_review_required"
    assert result["terminalTreeId"] == "bp_thresholds_targets"
    assert [step["treeId"] for step in result["steps"]] == ["bp_thresholds_targets"]
    assert result["linksVisited"] == []


def test_runtime_returns_structured_invalid_input_for_wrong_canonical_type() -> None:
    result = run(BUNDLE_PATH, "bp_diagnosis", {
        "bp.office1.systolicMmHg": "180",
    })
    assert result["status"] == "invalid_input"
    assert result["reason"] == "invalid_context"
    assert result["decision"]["errors"][0]["field"] == "bp.office1.systolicMmHg"
