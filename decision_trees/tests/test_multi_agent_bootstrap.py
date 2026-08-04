#!/usr/bin/env python3
"""Offline contract test for image -> multi-agent draft bundle orchestration."""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decision_trees.pipeline.multi_agent_pipeline import GeminiClient, build_extraction_context, main
from decision_trees.runtime.validate_decision_tree_bundle import validate_bundle


def source_ref(source_id: str, filename: str) -> dict[str, object]:
    return {
        "sourceId": source_id,
        "page": 1,
        "section": "Mock evidence",
        "tableOrFigure": filename,
        "note": "Offline orchestration test.",
    }


def fake_generate_json(self: GeminiClient, role: str, prompt: str, schema: dict, image_paths=None) -> dict:
    del self, schema, image_paths
    if role.startswith("evidence:"):
        tree_id = role.split(":", 1)[1]
        return {
            "treeId": tree_id,
            "claims": [],
            "missingEvidence": [],
        }
    if role.startswith("variable-architect"):
        return {
            "variablesJson": json.dumps([
                {
                    "id": "mock.input",
                    "label": "Mock input",
                    "dataType": "enum",
                    "allowedValues": ["yes", "no"],
                    "unit": None,
                    "definition": "Offline test input.",
                    "sourceSystem": "clinician_input",
                    "sourceRefsJson": json.dumps([source_ref("image_01_bp_diagnosis", "01_bp_diagnosis.png")]),
                    "derivedFromJson": "[]",
                }
            ]),
            "derivationRulesJson": "[]",
            "warnings": [],
        }
    if role.startswith("builder:") or role.startswith("repair:"):
        tree_id = role.split(":")[-1]
        source_id = {
            "bp_diagnosis": "image_01_bp_diagnosis",
            "bp_thresholds_targets": "image_02_bp_thresholds_targets",
            "optimized_hypertension_treatment": "image_03_optimized_treatment",
            "hypertension_risk_stratification": "image_04_risk_stratification",
            "uncontrolled_resistant_hypertension": "image_05_uncontrolled_resistant",
        }[tree_id]
        filename = {
            "bp_diagnosis": "01_bp_diagnosis.png",
            "bp_thresholds_targets": "02_bp_thresholds_and_targets.png",
            "optimized_hypertension_treatment": "03_optimized_hypertension_treatment.png",
            "hypertension_risk_stratification": "04_hypertension_risk_stratification.png",
            "uncontrolled_resistant_hypertension": "05_uncontrolled_resistant_hypertension.png",
        }[tree_id]
        ref = source_ref(source_id, filename)
        predicate = {"field": "mock.input", "op": "eq", "value": "yes"}
        return {
            "id": tree_id,
            "name": tree_id,
            "purpose": "Offline test tree.",
            "entryNodeId": "start",
            "inputVariables": ["mock.input"],
            "outputVariables": [],
            "linksTo": [],
            "nodes": [
                {"id": "start", "type": "start", "display": {"title": "Start", "detail": "", "shortLabel": "Start"}, "logicJson": "{}", "dataJson": "{}", "sourceRefs": [ref]},
                {"id": "condition", "type": "condition", "display": {"title": "Mock condition", "detail": "", "shortLabel": "Condition"}, "logicJson": json.dumps({"predicate": predicate}), "dataJson": "{}", "sourceRefs": [ref]},
                {"id": "end_yes", "type": "end", "display": {"title": "Mock result", "detail": "", "shortLabel": "Result"}, "logicJson": "{}", "dataJson": json.dumps({"outcomeCode": "mock_result"}), "sourceRefs": [ref]},
            ],
            "edges": [
                {"from": "start", "to": "condition", "when": "default"},
                {"from": "condition", "to": "end_yes", "when": "true", "label": "yes"},
                {"from": "condition", "to": "end_yes", "when": "false", "label": "no"},
            ],
            "sourceRefs": [ref],
            "notes": [],
        }
    if role.startswith("verifier:"):
        return {
            "treeId": role.split(":")[-1],
            "status": "pass",
            "issues": [],
            "coverageJson": json.dumps({"totalClaims": 0, "coveredClaims": [], "uncoveredClaims": [], "coverageRatio": 1.0, "coveragePercentage": 100}),
            "missingDataJson": json.dumps({"missingVariables": [], "missingItems": []}),
        }
    if role == "manager":
        tree_ids = [
            "bp_diagnosis",
            "bp_thresholds_targets",
            "optimized_hypertension_treatment",
            "hypertension_risk_stratification",
            "uncontrolled_resistant_hypertension",
        ]
        return {
            "status": "ready_for_review",
            "approvedTreeIdsJson": json.dumps(tree_ids),
            "requiredFixesJson": "[]",
            "variableChangesJson": "[]",
            "finalNotesJson": "[]",
        }
    raise AssertionError(f"unexpected mock role: {role}")


def main_test() -> None:
    context, image_map = build_extraction_context()
    assert len(context["sourceDocuments"]) == 5
    assert context["variables"] == []
    assert len(context["trees"]) == 5
    assert all(path.exists() for path in image_map.values())

    with TemporaryDirectory() as temporary:
        out_dir = Path(temporary) / "run"
        argv = [
            "multi_agent_pipeline.py",
            "--out-dir", str(out_dir),
            "--max-rounds", "2",
            "--dotenv", str(Path(temporary) / "missing.env"),
        ]
        with patch.dict("os.environ", {"GEMINI_KEY": "offline-test-key"}, clear=False), patch.object(GeminiClient, "generate_json", fake_generate_json), patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
            main()

        report = json.loads((out_dir / "run_report.json").read_text(encoding="utf-8"))
        assert report["loopStatus"] == "passed"
        assert report["roundsCompleted"] == 1
        draft = out_dir / "bundle.draft.json"
        assert draft.exists()
        assert validate_bundle(draft) == {"trees": 5, "variables": 1, "nodes": 15, "edges": 15, "links": 0}

    print("multi-agent bootstrap tests: ok")


if __name__ == "__main__":
    main_test()
