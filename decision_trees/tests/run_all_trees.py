#!/usr/bin/env python3
"""Run one representative completed case for each active decision tree."""

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
        "bp.office1.systolicMmHg": 130,
        "bp.office1.diastolicMmHg": 80,
        "bp.office2.systolicMmHg": 130,
        "bp.office2.diastolicMmHg": 80,
        "bp.office3.systolicMmHg": 125,
        "bp.office3.diastolicMmHg": 80,
        "patient.diagnosisCodes": "",
    },
    "bp_thresholds_targets": {
        "bp.category": "high_normal",
        "patient.diagnosisCodes": "",
        "comorbidity.targetOrganDamageOrCvd": False,
        "encounter.number": 2,
    },
    "optimized_hypertension_treatment": {
        "patient.birthDate": "1990-01-01",
        "asOf": "2026-08-11",
        "bp.category": "hypertension",
        "treatment.recommendation": "medication_now",
        "comorbidity.targetOrganDamageOrCvd": False,
        "patient.ageYears": 36,
        "encounter.number": 2,
        "patient.diagnosisCodes": "",
        "medication.previousEncounterDrugNames": "Losartan, amlodipine",
        "bp.controlledAfterTwoDrugs": False,
        "bp.controlledAfterThreeDrugs": False,
        "bp.controlledAfterFourDrugs": False,
    },
    "hypertension_risk_stratification": {
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
    },
    "uncontrolled_resistant_hypertension": {
        "asOf": "2026-08-12",
        "bp.office3.systolicMmHg": 150,
        "bp.office3.diastolicMmHg": 95,
        "medication.regimenStartDate": "2026-07-14",
        "medication.currentDrugNames": "Losartan, amlodipine",
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
