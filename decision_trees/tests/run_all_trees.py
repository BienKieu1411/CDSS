#!/usr/bin/env python3
"""Run one representative completed case for each image-target tree."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decision_trees.config.paths import BUNDLE_PATH, PROJECT_ROOT
from decision_trees.runtime.decision_tree_engine import run


RESULTS_DIR = PROJECT_ROOT / "results"

TEST_CASES = {
    "bp_diagnosis": {
        "bp.measurementMethod": "office_3rd",
        "bp.office1.systolicMmHg": 130,
        "bp.office1.diastolicMmHg": 80,
        "bp.office1.targetOrganDamageOrCvd": False,
        "bp.office2.systolicMmHg": 130,
        "bp.office2.diastolicMmHg": 80,
        "bp.office2.targetOrganDamageOrCvd": False,
        "bp.office3.systolicMmHg": 125,
        "bp.office3.diastolicMmHg": 80,
    },
    "bp_thresholds_targets": {
        "bp.category": "high_normal",
        "risk.class": "high",
        "treatment.hasHighRiskComorbidity": True,
    },
    "optimized_hypertension_treatment": {
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
    },
    "hypertension_risk_stratification": {
        "bp.category": "grade1",
        "bp.systolicMmHg": 150,
        "bp.diastolicMmHg": 95,
        "risk.factorCount": 3,
        "risk.highRiskComorbidity": False,
    },
    "uncontrolled_resistant_hypertension": {
        "bp.officeAverageSystolicMmHg": 150,
        "bp.officeReadingCount": 2,
        "medication.regimenStableWeeks": 4,
        "medication.agentCount": 3,
        "medication.includesDiuretic": True,
        "resistant.egfrMlMin": 60,
        "resistant.potassiumMmolL": 4.2,
        "resistant.sodiumMmolL": 140,
        "pregnancy.status": "not_pregnant",
        "resistant.severeLiverDisease": False,
        "resistant.systolicDropAt12WeeksMmHg": 9.0,
    },
}


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summaries = []
    for tree_id, variables in TEST_CASES.items():
        result = run(BUNDLE_PATH, tree_id, variables)
        output = {
            "treeId": tree_id,
            "testInput": variables,
            "result": result,
        }
        output_path = RESULTS_DIR / f"{tree_id}.json"
        output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        status = result.get("status")
        if status != "completed":
            raise RuntimeError(f"{tree_id} did not complete: {status}; {result.get('missingData', [])}")
        summaries.append({
            "treeId": tree_id,
            "status": status,
            "outcomeCode": result.get("outcomeCode"),
            "resultCode": result.get("resultCode"),
            "linksVisited": result.get("linksVisited", []),
            "output": str(output_path),
        })
    print(json.dumps({"status": "ok", "trees": summaries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
