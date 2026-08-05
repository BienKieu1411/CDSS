#!/usr/bin/env python3
"""Multi-agent Gemini pipeline for automatic guideline -> decision-tree drafts.

Pipeline:
  evidence agents (parallel)
      -> variable architect
      -> variable verifier/repair loop
      -> tree builders (parallel)
      -> tree verifier/repair loop
      -> manager/aggregator
      -> local validator and versioned draft bundle

The output bundle is always marked ``under_review``. No LLM output is treated as
clinically approved, and the reviewed baseline is never overwritten automatically.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import json
import os
import random
import re
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decision_trees.config.paths import (
    DECISION_ROOT,
    EXTRACTION_MANIFEST_PATH,
    IMAGES_DIR,
    PASS_CRITERIA_PATH,
    PROJECT_ROOT as WORKSPACE_ROOT,
)
from decision_trees.pipeline.create_decision_tree_example import validate_exemplar
from decision_trees.pipeline.generate_decision_tree import (
    MAX_RESPONSE_BYTES,
    GeminiCallError,
    NormalisationError,
    file_sha256,
    normalise_tree,
    reduced_response_schema,
    safe_error,
    semantic_check,
    stable_hash,
)
from decision_trees.runtime.validate_decision_tree_bundle import validate_bundle


ROOT = DECISION_ROOT
PROJECT_ROOT = WORKSPACE_ROOT
DEFAULT_EXEMPLAR = ROOT / "bundle" / "decision_tree_example.json"
DEFAULT_PASS_CRITERIA = PASS_CRITERIA_PATH
PIPELINE_VERSION = "multi-agent-pipeline.v2"
PROMPT_VERSION = "prompts.v2"
CANONICAL_SOURCE_SYSTEMS = {"patient", "encounter", "vitals", "laboratory", "medication", "problem_list", "derived", "clinician_input"}


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_extraction_context(manifest_path: Path = EXTRACTION_MANIFEST_PATH) -> tuple[dict[str, Any], dict[str, Path]]:
    """Create an empty bundle context from evidence files, not a clinical baseline.

    The manifest identifies which image belongs to each requested tree. It does
    not contain variables, predicates, nodes, edges, outcomes, or clinical
    recommendations. Those are produced by the agents and checked later.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("manifestVersion") != "decision-tree-extraction-manifest.v1":
        raise ValueError("invalid extraction manifest version")
    raw_sources = manifest.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("extraction manifest must contain sources")

    source_documents: list[dict[str, Any]] = []
    trees: list[dict[str, Any]] = []
    image_paths: dict[str, Path] = {}
    source_ids: set[str] = set()
    tree_ids: set[str] = set()
    for index, item in enumerate(raw_sources):
        if not isinstance(item, dict):
            raise ValueError(f"sources[{index}] must be an object")
        tree_id = item.get("treeId")
        source_id = item.get("sourceId")
        filename = item.get("file")
        title = item.get("title")
        purpose = item.get("purpose")
        if not all(isinstance(value, str) and value.strip() for value in (tree_id, source_id, filename, title, purpose)):
            raise ValueError(f"sources[{index}] requires treeId, sourceId, file, title and purpose")
        if tree_id in tree_ids:
            raise ValueError(f"duplicate treeId {tree_id}")
        if source_id in source_ids:
            raise ValueError(f"duplicate sourceId {source_id}")
        image_path = IMAGES_DIR / filename
        if not image_path.exists():
            raise ValueError(f"missing evidence image: {image_path}")
        tree_ids.add(tree_id)
        source_ids.add(source_id)
        image_paths[tree_id] = image_path
        source_ref = {
            "sourceId": source_id,
            "page": 1,
            "section": title,
            "tableOrFigure": filename,
            "note": "Evidence image supplied to the extraction agents.",
        }
        source_documents.append({
            "id": source_id,
            "title": title,
            "version": "image-reference",
            "localFile": f"decision_trees/images/{filename}",
        })
        trees.append({
            "id": tree_id,
            "name": title,
            "purpose": purpose,
            "clinicalStatus": "under_review",
            "entryNodeId": "",
            "inputVariables": [],
            "outputVariables": [],
            "linksTo": [],
            "nodes": [],
            "edges": [],
            "sourceRefs": [source_ref],
            "notes": ["Generated from the supplied evidence image; clinical review is required."],
        })

    context = {
        "formatVersion": "decision-tree-bundle.v1",
        "bundleId": "gemini-image-extraction",
        "bundleVersion": "0.0.0",
        "locale": manifest.get("locale", "vi-VN"),
        "clinicalStatus": "under_review",
        "clinicalReviewRequired": True,
        "sourceDocuments": source_documents,
        "variables": [],
        "trees": trees,
    }
    return context, image_paths


def extract_pages(pdf_path: Path, pages: list[int]) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    chunks = []
    seen: set[int] = set()
    for page_number in pages:
        if page_number in seen:
            continue
        seen.add(page_number)
        if page_number < 1 or page_number > len(reader.pages):
            raise ValueError(f"Page {page_number} is outside {pdf_path.name}")
        text = reader.pages[page_number - 1].extract_text() or ""
        if not text.strip():
            raise ValueError(f"Page {page_number} has no extractable text; OCR is required before generation")
        chunks.append(f"[SOURCE PAGE {page_number}]\n{text}")
    return "\n\n".join(chunks)


def strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


class GeminiClient:
    def __init__(self, api_key: str, model: str, retries: int = 3):
        self.api_key = api_key
        self.model = model
        self.retries = retries

    def generate_json(self, role: str, prompt: str, schema: dict[str, Any], image_paths: list[Path] | None = None) -> dict[str, Any]:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        parts: list[dict[str, Any]] = [{"text": prompt}]
        for image_path in image_paths or []:
            mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
            parts.append({"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_path.read_bytes()).decode("ascii")}})
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": schema,
                "temperature": 0.0,
            },
        }
        encoded_payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last_error: GeminiCallError | None = None
        for attempt in range(1, self.retries + 1):
            request = urllib.request.Request(
                endpoint,
                data=encoded_payload,
                headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=240) as response:
                    raw_body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw_body) > MAX_RESPONSE_BYTES:
                    raise GeminiCallError(role, "response_too_large", attempts=attempt)
                body = json.loads(raw_body.decode("utf-8"))
                candidates = body.get("candidates") if isinstance(body, dict) else None
                if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
                    raise GeminiCallError(role, "missing_candidate", retryable=True, attempts=attempt)
                candidate = candidates[0]
                finish_reason = candidate.get("finishReason")
                if finish_reason not in (None, "STOP"):
                    raise GeminiCallError(role, f"generation_not_complete:{finish_reason}", attempts=attempt)
                content = candidate.get("content")
                parts = content.get("parts") if isinstance(content, dict) else None
                text = parts[0].get("text") if isinstance(parts, list) and parts and isinstance(parts[0], dict) else None
                if not isinstance(text, str) or not text.strip():
                    raise GeminiCallError(role, "missing_structured_text", retryable=True, attempts=attempt)
                parsed = json.loads(strip_fences(text))
                if not isinstance(parsed, dict):
                    raise GeminiCallError(role, "structured_output_not_object", attempts=attempt)
                return parsed
            except GeminiCallError as exc:
                last_error = exc
            except urllib.error.HTTPError as exc:
                status = exc.code
                last_error = GeminiCallError(role, f"http_{status}", retryable=status in {408, 425, 429, 500, 502, 503, 504}, attempts=attempt, http_status=status)
            except (urllib.error.URLError, TimeoutError, OSError):
                last_error = GeminiCallError(role, "transport_error", retryable=True, attempts=attempt)
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError):
                last_error = GeminiCallError(role, "malformed_provider_response", retryable=True, attempts=attempt)
            if last_error.retryable and attempt < self.retries:
                retry_delay = 12.0 * attempt if last_error.code == "http_429" else min(30.0, 2 ** (attempt - 1))
                time.sleep(retry_delay + random.uniform(0.0, 0.25))
                continue
            break
        if last_error is None:
            last_error = GeminiCallError(role, "unknown_api_error", attempts=self.retries)
        raise last_error


def simple_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


def evidence_schema() -> dict[str, Any]:
    claim = {
        "type": "object",
        "properties": {
            "claimId": {"type": "string"},
            "claim": {"type": "string"},
            "predicateJson": {"type": "string"},
            "variablesJson": {"type": "string"},
            "sourceRefsJson": {"type": "string"},
            "confidence": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["claimId", "claim", "predicateJson", "variablesJson", "sourceRefsJson", "confidence", "notes"],
    }
    return simple_schema(
        {"treeId": {"type": "string"}, "claims": {"type": "array", "items": claim}, "missingEvidence": {"type": "array", "items": {"type": "string"}}},
        ["treeId", "claims", "missingEvidence"],
    )


def variable_schema() -> dict[str, Any]:
    source_ref = {
        "type": "object",
        "properties": {
            "sourceId": {"type": "string"},
            "page": {"type": "integer"},
            "section": {"type": "string"},
            "tableOrFigure": {"type": "string"},
            "note": {"type": "string"},
        },
        "required": ["sourceId", "page", "section", "tableOrFigure", "note"],
    }
    variable = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "label": {"type": "string"},
            "dataType": {"enum": ["boolean", "integer", "number", "string", "enum"]},
            "unit": {"type": "string"},
            "definition": {"type": "string"},
            "sourceSystem": {"enum": sorted(CANONICAL_SOURCE_SYSTEMS)},
            "allowedValues": {"type": "array", "items": {}},
            "requiredForEvaluation": {"type": "boolean"},
            "sourceRefs": {"type": "array", "items": source_ref},
            "derivedFrom": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["id", "label", "dataType", "unit", "definition", "sourceSystem", "sourceRefs", "derivedFrom", "requiredForEvaluation"],
    }
    return simple_schema(
        {"variablesJson": {"type": "array", "items": variable}, "derivationRulesJson": {"type": "string"}, "warnings": {"type": "array", "items": {"type": "string"}}},
        ["variablesJson", "derivationRulesJson", "warnings"],
    )


def variable_verifier_schema() -> dict[str, Any]:
    issue = {
        "type": "object",
        "properties": {
            "severity": {"type": "string"},
            "variableId": {"type": "string"},
            "message": {"type": "string"},
            "sourceRef": {"type": "string"},
            "suggestedFix": {"type": "string"},
        },
        "required": ["severity", "variableId", "message", "sourceRef", "suggestedFix"],
    }
    return simple_schema(
        {
            "treeId": {"type": "string"},
            "status": {"type": "string"},
            "issues": {"type": "array", "items": issue},
            "coverageJson": {"type": "string"},
            "missingVariablesJson": {"type": "string"},
            "invalidVariablesJson": {"type": "string"},
            "notes": {"type": "string"},
        },
        ["treeId", "status", "issues", "coverageJson", "missingVariablesJson", "invalidVariablesJson", "notes"],
    )


def verifier_schema() -> dict[str, Any]:
    issue = {
        "type": "object",
        "properties": {"severity": {"type": "string"}, "nodeId": {"type": "string"}, "message": {"type": "string"}, "sourceRef": {"type": "string"}, "suggestedFix": {"type": "string"}},
        "required": ["severity", "nodeId", "message", "sourceRef", "suggestedFix"],
    }
    return simple_schema(
        {"treeId": {"type": "string"}, "status": {"type": "string"}, "issues": {"type": "array", "items": issue}, "coverageJson": {"type": "string"}, "missingDataJson": {"type": "string"}},
        ["treeId", "status", "issues", "coverageJson", "missingDataJson"],
    )


def manager_schema() -> dict[str, Any]:
    return simple_schema(
        {"status": {"type": "string"}, "approvedTreeIdsJson": {"type": "string"}, "requiredFixesJson": {"type": "string"}, "variableChangesJson": {"type": "string"}, "finalNotesJson": {"type": "string"}},
        ["status", "approvedTreeIdsJson", "requiredFixesJson", "variableChangesJson", "finalNotesJson"],
    )


def evidence_prompt(tree: dict[str, Any], source_text: str, bundle: dict[str, Any]) -> str:
    preferred_aliases = {
        "bp_diagnosis": [
            "ha_pk_1_systolic", "ha_pk_1_diastolic", "ha_pk_2_systolic", "ha_pk_2_diastolic",
            "ha_pk_3_systolic", "ha_pk_3_diastolic", "target_organ_damage_or_cvd", "hatn_systolic",
            "hatn_diastolic", "halt_day_systolic", "halt_day_diastolic", "halt_24h_systolic", "halt_24h_diastolic",
        ],
        "bp_thresholds_targets": ["HATT", "HATTr", "target_HATT", "target_HATTr", "BĐM", "BTMXV", "ĐTĐ", "BTM"],
        "optimized_hypertension_treatment": [
            "age", "bp_systolic", "bp_diastolic", "bp_category", "risk_level", "frailty_syndrome",
            "has_cvd", "has_ckd", "has_diabetes", "treatment_step", "resistant_hypertension",
            "additional_medication", "compulsory_indication", "blood_pressure_controlled",
        ],
        "hypertension_risk_stratification": [
            "HATT", "HATTr", "YTNC_count", "has_TOD_CVD_DM", "age", "gender", "heart_rate", "overweight",
            "diabetes", "LDL_C", "triglyceride", "family_history_cvd", "family_history_hypertension",
            "early_menopause", "smoking", "socioeconomic_risk_factors", "LVH_ECG", "eGFR", "other_TOD",
            "coronary_heart_disease", "heart_failure", "stroke", "peripheral_artery_disease", "atrial_fibrillation", "ckd_stage",
        ],
        "uncontrolled_resistant_hypertension": [
            "seated_sbp", "regimen_stable_weeks", "antihypertensive_agents_count", "includes_diuretic", "eGFR",
            "K+", "Na+", "pregnancy", "liver", "sbp_decrease_12_wks_mmhg",
        ],
    }.get(tree["id"], [])
    return f"""Role: Evidence Extractor Agent.
Extract only guideline evidence needed for tree '{tree['id']}'. Do not design the tree yet.
For every claim, output a machine-readable predicateJson using one of the preferred evidence identifiers below, plus sourceRefsJson with exact sourceId and page/section/tableOrFigure. Do not invent transliterated, Vietnamese, or composite aliases when a preferred identifier exists. If a blood-pressure threshold is shown, use separate systolic and diastolic identifiers; never use a single composite variable such as ha_phong_kham, blood_pressure, or a string like 140/90.
Preferred evidence identifiers for this tree: {json.dumps(preferred_aliases, ensure_ascii=False)}
If the source is a matrix or table, emit one claim for every clinically distinct row/column cell and preserve all category combinations; do not summarize the whole matrix as one claim.
Capture thresholds, inclusivity, exceptions, and missing-data requirements. Only put an item in missingEvidence when the supplied image omits information that is necessary to implement a pictured branch. Do not mark ancillary guideline thresholds as missing when the image provides a categorical input such as a risk-factor count or a named comorbidity.
Existing source catalog: {json.dumps(bundle['sourceDocuments'], ensure_ascii=False)}
Existing variable catalog: {json.dumps([v['id'] for v in bundle['variables']], ensure_ascii=False)}
Tree purpose: {tree['purpose']}
Guideline text:
{source_text}
Return JSON only."""


def evidence_report_errors(report: Any) -> list[str]:
    """Check transport-level evidence shape before variable extraction starts."""
    if not isinstance(report, dict):
        return ["evidence report is missing or invalid"]
    claims = report.get("claims")
    if not isinstance(claims, list) or not claims:
        return ["evidence claims must be a non-empty array"]
    errors: list[str] = []
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            errors.append(f"claims[{index}] must be an object")
            continue
        claim_id = claim.get("claimId", index)
        for key in ("predicateJson", "variablesJson", "sourceRefsJson"):
            parsed = decode_json_value(claim.get(key), None)
            if parsed is None:
                errors.append(f"evidence claim {claim_id}: {key} is invalid JSON")
        predicate = decode_json_value(claim.get("predicateJson"), None)
        if predicate is not None and not isinstance(predicate, dict):
            errors.append(f"evidence claim {claim_id}: predicateJson must decode to an object")
    if not isinstance(report.get("missingEvidence"), list):
        errors.append("missingEvidence must be an array")
    return errors


def evidence_variable_names(report: Any) -> set[str]:
    names: set[str] = set()
    if not isinstance(report, dict) or not isinstance(report.get("claims"), list):
        return names
    for claim in report["claims"]:
        if not isinstance(claim, dict):
            continue
        values = decode_json_value(claim.get("variablesJson"), [])
        if isinstance(values, dict):
            raw_names = list(values)
        elif isinstance(values, list):
            raw_names = [
                item if isinstance(item, str) else item.get("name")
                for item in values
                if isinstance(item, str) or isinstance(item, dict) and isinstance(item.get("name"), str)
            ]
        else:
            raw_names = []
        for name in raw_names:
            if not isinstance(name, str):
                continue
            normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
            names.add(re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_"))
    return names


def evidence_completeness_errors(report: Any, tree_id: str, pass_criteria: dict[str, Any]) -> list[str]:
    """Require the evidence agent to cover the pictured tree before variables can pass."""
    rules = pass_criteria.get("evidence", {}) if isinstance(pass_criteria, dict) else {}
    claims = report.get("claims") if isinstance(report, dict) else None
    if not isinstance(claims, list):
        return []
    errors: list[str] = []
    minimum = rules.get("minimumClaimsByTree", {}).get(tree_id)
    if isinstance(minimum, int) and len(claims) < minimum:
        errors.append(f"evidence has {len(claims)} claim(s), strict minimum is {minimum}")
    names = evidence_variable_names(report)
    groups = rules.get("requiredAliasGroupsByTree", {}).get(tree_id, [])
    for index, group in enumerate(groups):
        normalized_group = {
            re.sub(r"[^a-z0-9]+", "_", unicodedata.normalize("NFKD", str(alias)).encode("ascii", "ignore").decode("ascii").lower()).strip("_")
            for alias in group
        }
        if names.isdisjoint(normalized_group):
            errors.append(f"evidence is missing required branch variable group {index + 1}: {sorted(group)}")
    return errors


def evidence_repair_prompt(tree: dict[str, Any], evidence: dict[str, Any], errors: list[str], source_text: str, bundle: dict[str, Any]) -> str:
    return f"""Role: Evidence Repair Agent.
Repair the evidence report for tree '{tree['id']}' before variable extraction.
This is a transport and extraction repair only: preserve every clinically
distinct claim supported by the attached image, but correct malformed nested
JSON strings, invalid predicate shapes, and non-atomic variable references.
Use a predicate AST with only these forms: {{"field":"alias","op":"gte","value":130}},
{{"all":[leaf,...]}}, or {{"any":[leaf,...]}}. Each blood-pressure threshold
must use separate systolic and diastolic aliases; never use a composite reading.
Do not treat a treatment recommendation (for example A+B or C) as a variable.
Return the complete evidence report, not a patch. Use exact source IDs from the
source catalog and keep missingEvidence empty unless the image truly omits a
branch-defining fact.

LOCAL ERRORS:
{json.dumps(errors, ensure_ascii=False)}

CURRENT REPORT:
{json.dumps(evidence, ensure_ascii=False)}

SOURCE CATALOG:
{json.dumps(bundle.get('sourceDocuments', []), ensure_ascii=False)}

REFERENCE IMAGE:
{source_text}

Return JSON only."""


def variable_prompt(evidence: dict[str, Any], bundle: dict[str, Any], tree_id: str | None = None) -> str:
    scope = f"for tree '{tree_id}'" if tree_id else "for the requested trees"
    tree_requirements = {
        "bp_thresholds_targets": "BTMXV, ĐTĐ, and BTM are three distinct boolean comorbidity variables; BĐM is a separate target-organ-damage/comorbidity flag. Never collapse these four evidence identifiers into one generic variable.",
        "hypertension_risk_stratification": "Keep HATT, HATTr, YTNC_count, TOD/CVD/DM, and every named risk factor/comorbidity as distinct variables. Do not replace a named factor with one aggregate risk boolean.",
        "uncontrolled_resistant_hypertension": "Keep seated_sbp, medication count, includes_diuretic, eGFR, K+, Na+, pregnancy, liver, and 12-week SBP decrease as distinct variables with their own data types.",
        "optimized_hypertension_treatment": "Keep cardiovascular disease, CKD, diabetes, resistant hypertension, treatment step, BP controlled, additional medication, and compulsory indication as distinct variables; do not merge named comorbidities into one generic flag.",
    }.get(tree_id or "", "")
    return f"""Role: Variable Architect Agent.
Build a draft variable catalog {scope} from the evidence pack. This is a bootstrap run: the existing catalog may be empty. Create every variable needed by the target tree, including variables written by inference/end nodes. Do not omit a variable merely because it appears in another tree; shared variables may be repeated and will be deduplicated by the aggregator.
Return variablesJson as a JSON array of variable objects, not as a JSON-encoded string. Every variable must include id, label, dataType, unit, definition, sourceSystem, requiredForEvaluation, sourceRefs, and derivedFrom. Use only these dataType values: boolean, integer, number, string, enum. Use only these sourceSystem values: patient, encounter, vitals, laboratory, medication, problem_list, derived, clinician_input. Variable IDs must match ^[a-z][a-zA-Z0-9]*(\\.[a-zA-Z0-9_]+)*$ and use ASCII letters/numbers in the first segment. Use dot-separated IDs such as bp.systolicMmHg, bp.diastolicMmHg, bp.officeVisit1.systolicMmHg, target.organDamagePresent, and risk.cardiovascularRisk. Never use Vietnamese words/accents, spaces, hyphens, or underscore-separated IDs such as ha_phong_kham_lan_1_sys; represent that concept as bp.officeVisit1.systolicMmHg. For enum variables include allowedValues. Every sourceRef must be an object with the exact sourceId and tableOrFigure filename from the source catalog. Distinguish raw input variables from derived variables. Include derivation rules as a JSON string.
   Every variable used with gt/gte/lt/lte must have dataType number or integer. Blood pressure values must be represented as separate numeric systolic and diastolic variables; never represent a BP reading used in a threshold predicate as one string/composite variable. A unit of mmHg is not sufficient to make a composite string computable.
Tree-specific invariants: {tree_requirements}
Existing catalog: {json.dumps(bundle['variables'], ensure_ascii=False)}
Evidence pack: {json.dumps(evidence, ensure_ascii=False)}
Source catalog: {json.dumps(bundle['sourceDocuments'], ensure_ascii=False)}
Return JSON only. Do not write executable code or free-text clinical rules."""


def variable_verifier_prompt(tree_id: str, proposal: dict[str, Any], evidence: dict[str, Any], bundle: dict[str, Any], local_errors: list[str]) -> str:
    return f"""Role: Variable Catalog Verifier Agent.
Audit the variable catalog for tree '{tree_id}' before any tree builder is allowed to run.
This is a variable-only audit; do not design nodes or edges. Compare the complete
proposal with every evidence claim and predicate. Detect missing variables,
wrong IDs, wrong data types, wrong units, invalid enum values, composite blood
pressure strings, unsupported source systems, duplicate/conflicting definitions,
undeclared derived inputs, and incorrect source references. A threshold on
systolic/diastolic blood pressure requires separate numeric variables.
Report every problem with severity P0/P1/P2 and a concrete fix. Status is pass
only when there are no issues and the catalog fully covers the evidence needed
for the target tree. Do not silently repair the proposal.

The next variable agent will receive your complete response, so make messages
actionable and identify the exact variable ID or missing variable to add.

LOCAL CANONICAL-NORMALIZER ERRORS:
{json.dumps(local_errors, ensure_ascii=False)}

PROPOSAL:
{json.dumps(proposal, ensure_ascii=False)}

EVIDENCE PACK:
{json.dumps(evidence, ensure_ascii=False)}

CURRENT SHARED CATALOG:
{json.dumps(bundle.get('variables', []), ensure_ascii=False)}

SOURCE CATALOG:
{json.dumps(bundle.get('sourceDocuments', []), ensure_ascii=False)}

Required response contracts:
- issues is [] only when the catalog is complete and correct.
- coverageJson decodes to an object with totalClaims, coveredClaims, uncoveredClaims,
  coverageRatio, and coveragePercentage. Use 1.0 and 100 only when complete.
- missingVariablesJson and invalidVariablesJson each decode to arrays and must be [] to pass.
Return JSON only."""


def variable_repair_prompt(tree_id: str, proposal: dict[str, Any], verification: dict[str, Any], evidence: dict[str, Any], bundle: dict[str, Any], local_errors: list[str]) -> str:
    tree_requirements = {
        "bp_thresholds_targets": "BTMXV, ĐTĐ, BTM, and BĐM must remain distinct variables; do not repair them into one generic comorbidity flag.",
        "hypertension_risk_stratification": "Keep the blood-pressure pair, YTNC_count, TOD/CVD/DM, and each named risk factor/comorbidity as distinct variables.",
        "uncontrolled_resistant_hypertension": "Keep each safety-screen variable and treatment-count variable distinct; never merge K+, Na+, eGFR, pregnancy, liver, or SBP decrease.",
        "optimized_hypertension_treatment": "Keep cardiovascular disease, CKD, diabetes, resistant hypertension, treatment step, BP controlled, additional medication, and compulsory indication distinct.",
    }.get(tree_id, "")
    return f"""Role: Variable Catalog Repair Agent.
Repair the complete variable catalog for tree '{tree_id}' using only the
evidence and the verifier findings below. Return the full variablesJson array,
including every previously valid variable; never return only a patch. Add
missing variables, correct wrong data types/units/source systems/allowed values,
and remove unsupported or duplicate variables when the verifier identifies them.
Preserve exact canonical IDs that are already valid. Rename every invalid ID to
an ASCII dot-separated canonical ID; never preserve an underscore-separated or
Vietnamese ID. For example, ha_phong_kham_lan_1_sys must become
bp.officeVisit1.systolicMmHg. Variable IDs must match
^[a-z][a-zA-Z0-9]*(\\.[a-zA-Z0-9_]+)*$. Numeric comparisons require number or
integer. Blood pressure thresholds require separate numeric systolic and
diastolic variables, never a composite string. Every variable needs a precise
sourceRef to the supplied image. Do not create nodes, edges, executable code,
or unsupported clinical rules.
Tree-specific invariant: {tree_requirements}

LOCAL ERRORS:
{json.dumps(local_errors, ensure_ascii=False)}

VERIFIER FINDINGS:
{json.dumps(verification, ensure_ascii=False)}

PREVIOUS COMPLETE PROPOSAL:
{json.dumps(proposal, ensure_ascii=False)}

EVIDENCE PACK:
{json.dumps(evidence, ensure_ascii=False)}

SHARED CATALOG:
{json.dumps(bundle.get('variables', []), ensure_ascii=False)}

SOURCE CATALOG:
{json.dumps(bundle.get('sourceDocuments', []), ensure_ascii=False)}
Return JSON only, using the exact variable schema."""


def tree_builder_prompt(tree: dict[str, Any], evidence: dict[str, Any], variable_proposal: dict[str, Any], bundle: dict[str, Any], exemplar: dict[str, Any]) -> str:
    return f"""Role: Decision Tree Builder Agent.
Create a reviewable draft for tree '{tree['id']}' from evidence. Preserve the canonical node types start/condition/inference/link/end.
This is a bootstrap extraction: the target template contains metadata only. Create the tree's inputVariables and outputVariables from the variable architect proposal and the supplied evidence. Every predicate field must be declared in the tree's inputVariables; every variable written by data.sets must be declared in outputVariables. Do not substitute a raw field from another tree. Every condition must contain logicJson whose parsed object has predicate; every inference/end/link must contain dataJson. Use exact numeric operators and no code.
Predicate syntax is strict: a leaf is exactly {{"field":"variable.id","op":"gte","value":130}}; a compound is exactly {{"all":[leaf,...]}} or {{"any":[leaf,...]}}. Do not use function notation such as {{"gte":[{{"var":"variable.id"}},130]}}, SQL, Python, or extra keys in a predicate object. `present` is the only operator without `value`.
Any field used with gt/gte/lt/lte must refer to a number/integer variable in the catalog. For blood pressure, use separate numeric systolic/diastolic variables and do not compare a composite string reading.
Every clinical node needs sourceRefs. If evidence is insufficient, emit needs_clinical_review and explain it in notes.
Use sourceId and tableOrFigure exactly as listed in the source catalog; do not shorten or rename image filenames. Graph rules are strict: condition nodes have exactly one true and one false edge; start and inference nodes have exactly one default edge; link and end nodes have no outgoing edge. Every node must be reachable from entryNodeId, and every clinical claim must be represented by a node/edge path.
Existing tree template: {json.dumps(tree, ensure_ascii=False)}
Evidence: {json.dumps(evidence, ensure_ascii=False)}
Variable proposal: {json.dumps(variable_proposal, ensure_ascii=False)}
ALLOWED VARIABLE IDS (copy exactly; no other IDs may appear in inputVariables, outputVariables, predicates, or data.sets): {json.dumps([v['id'] for v in bundle['variables']], ensure_ascii=False)}
If an output cannot be represented by an allowed variable, use resultCode/outcomeCode and do not invent a new output variable.

ONE-SHOT CANONICAL EXAMPLE:
The following is the canonical example of the required output shape. Copy its
structure and conventions, not its blood-pressure clinical content. Do not
copy a threshold into the target tree unless it is supported by the target
tree's evidence. Preserve the five node types, predicate AST, sourceRefs,
explicit edges, and safe missing-data behavior.
{json.dumps(exemplar, ensure_ascii=False)}

Return the tree JSON object only, using the structured-output fields logicJson/dataJson."""


def verifier_prompt(tree: dict[str, Any], evidence: dict[str, Any], bundle: dict[str, Any], pass_criteria: dict[str, Any]) -> str:
    return f"""Role: Clinical Logic Verifier Agent.
Audit the candidate tree against the guideline evidence. Check threshold inclusivity, branch completeness, contradictory/overlapping predicates, source coverage, link target validity, and missing-data safety. For a table or risk matrix, verify every clinically distinct cell/row/column combination is reachable and classified; a single summary claim is not sufficient coverage.
Do not silently repair it. Report each issue with severity P0/P1/P2 and a concrete suggestedFix. Status must be pass only if no P0/P1 issues remain.
Candidate tree: {json.dumps(tree, ensure_ascii=False)}
Evidence: {json.dumps(evidence, ensure_ascii=False)}
Available tree IDs: {json.dumps([t['id'] for t in bundle['trees']], ensure_ascii=False)}
STRICT PASS CRITERIA (all gates are mandatory):
{json.dumps(pass_criteria, ensure_ascii=False)}
The response fields must satisfy these exact machine contracts:
- issues must be an array and must be [] for pass.
- coverageJson must decode to an object containing totalClaims, coveredClaims (array), uncoveredClaims (array), coverageRatio (number), and coveragePercentage (number); use 1.0 and 100 when complete.
- missingDataJson must decode to an object containing missingVariables (array) and missingItems (array); use [] for both only when no missing-data issue remains.
Return JSON only."""


def repair_prompt(tree: dict[str, Any], verification: dict[str, Any], evidence: dict[str, Any], bundle: dict[str, Any], exemplar: dict[str, Any], pass_criteria: dict[str, Any]) -> str:
    return f"""Role: Decision Tree Repair Agent.
Repair only the candidate tree '{tree.get('id')}' using the verifier findings
and the supplied guideline evidence. Fix P0/P1 issues that are directly
supported by evidence; do not invent thresholds, variables, outcomes, or
source references. Preserve the tree ID, canonical node types, graph shape,
predicate AST, sourceRefs, and fail-closed missing-data behavior. If a finding
cannot be safely resolved from evidence, keep a safe needs_clinical_review path
and explain it in notes. Return the complete tree JSON only using logicJson and
dataJson string fields.
If the candidate object has status 'pipeline_error' or 'validation_error', it is
not a usable draft: regenerate the complete tree from the target template and
evidence instead of returning another error object. Predicate leaves must use
exactly {{"field":"variable.id","op":"gte","value":130}}; never emit
comparison-function notation, SQL, Python, or extra predicate keys.
Every predicate field must be declared in the target tree's inputVariables.

VERIFIER FINDINGS:
<DATA>
{json.dumps(verification, ensure_ascii=False)}
</DATA>

TARGET TREE:
<DATA>
{json.dumps(tree, ensure_ascii=False)}
</DATA>

GUIDELINE EVIDENCE:
<UNTRUSTED_GUIDELINE_EVIDENCE>
{json.dumps(evidence, ensure_ascii=False)}
</UNTRUSTED_GUIDELINE_EVIDENCE>

VARIABLE CATALOG:
<DATA>
{json.dumps(bundle.get('variables', []), ensure_ascii=False)}
</DATA>
The candidate may use only these exact variable IDs; never invent or rename one:
{json.dumps([item.get('id') for item in bundle.get('variables', []) if isinstance(item, dict)], ensure_ascii=False)}

ONE-SHOT FORMAT EXAMPLE (format only; never copy clinical content):
<DATA>
{json.dumps(exemplar, ensure_ascii=False)}
</DATA>

STRICT PASS CRITERIA:
<DATA>
{json.dumps(pass_criteria, ensure_ascii=False)}
</DATA>

Return JSON only."""


def manager_prompt(bundle: dict[str, Any], evidence: dict[str, Any], variable_proposal: dict[str, Any], variable_verifications: dict[str, Any], drafts: dict[str, Any], verifications: dict[str, Any], pass_criteria: dict[str, Any]) -> str:
    return f"""Role: Manager/Aggregator Agent.
Coordinate the multi-agent result. Decide whether the generated set is ready for human clinical review. You may approve a tree only when its verifier status is pass and its source coverage is adequate.
Do not approve missing or speculative evidence. Return approvedTreeIdsJson, requiredFixesJson, variableChangesJson, and finalNotesJson as valid JSON strings.
Status should be 'ready_for_review' only when all requested trees are structurally complete and no P0/P1 issue exists; otherwise 'blocked'.
Baseline bundle metadata: {json.dumps({'bundleId': bundle['bundleId'], 'bundleVersion': bundle['bundleVersion']}, ensure_ascii=False)}
Evidence pack: {json.dumps(evidence, ensure_ascii=False)}
Variable proposal: {json.dumps(variable_proposal, ensure_ascii=False)}
Variable verifier reports: {json.dumps(variable_verifications, ensure_ascii=False)}
Tree drafts: {json.dumps(drafts, ensure_ascii=False)}
Verifier reports: {json.dumps(verifications, ensure_ascii=False)}
Strict pass criteria: {json.dumps(pass_criteria, ensure_ascii=False)}
Return JSON only."""


def run_parallel(items: list[str], fn: Callable[[str], Any], max_workers: int) -> dict[str, Any]:
    results: dict[str, Any] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(fn, item): item for item in items}
        for future in concurrent.futures.as_completed(future_map):
            key = future_map[future]
            try:
                results[key] = future.result()
            except Exception as exc:
                results[key] = safe_error(exc)
    return results


def parse_json_string(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def decode_json_value(value: Any, fallback: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value


def canonical_variable_id(raw_id: str) -> tuple[str | None, str | None]:
    """Apply only lossless-ish syntax normalization to an LLM variable ID.

    Clinical meaning remains in the label/definition. This normalizer only
    makes separators and accents safe for the canonical identifier contract;
    every change is recorded in the run log and the resulting catalog is still
    sent through the variable verifier.
    """
    if re.fullmatch(r"[a-z][a-zA-Z0-9]*(\.[a-zA-Z0-9_]+)*", raw_id):
        return raw_id, None
    normalized = unicodedata.normalize("NFKD", raw_id).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", ".", normalized.replace("_", "."))
    normalized = re.sub(r"\.+", ".", normalized).strip(".")
    if normalized and not normalized[0].islower():
        normalized = normalized[0].lower() + normalized[1:]
    if normalized and normalized[0].isdigit():
        normalized = "v." + normalized
    if not re.fullmatch(r"[a-z][a-zA-Z0-9]*(\.[a-zA-Z0-9_]+)*", normalized):
        return None, None
    return normalized, f"{raw_id} -> {normalized}"


# Evidence agents often use short labels from the image (for example HATT or
# office_bp_systolic) before the variable architect has produced the canonical
# catalog. These are transport aliases only; the clinical bundle keeps the
# canonical IDs below. Keeping this map in one place lets the verifier inspect
# the same identifiers that the builder will receive.
EVIDENCE_VARIABLE_ALIASES: dict[str, dict[str, str | tuple[str, ...]]] = {
    "bp_diagnosis": {
        "ha_pk_1_systolic": "bp.officeVisit1.systolicMmHg",
        "ha_pk_1_diastolic": "bp.officeVisit1.diastolicMmHg",
        "ha_pk_2_systolic": "bp.officeVisit2.systolicMmHg",
        "ha_pk_2_diastolic": "bp.officeVisit2.diastolicMmHg",
        "ha_pk_3_systolic": "bp.officeVisit3.systolicMmHg",
        "ha_pk_3_diastolic": "bp.officeVisit3.diastolicMmHg",
        "target_organ_damage_or_cvd": "target.organDamageOrCvd",
        "hatn_systolic": "bp.home.systolicMmHg",
        "hatn_diastolic": "bp.home.diastolicMmHg",
        "halt_day_systolic": ("bp.ambulatoryDay.systolicMmHg", "bp.ambulatory.daySystolicMmHg"),
        "halt_day_diastolic": ("bp.ambulatoryDay.diastolicMmHg", "bp.ambulatory.dayDiastolicMmHg"),
        "halt_24h_systolic": ("bp.ambulatory24h.systolicMmHg", "bp.ambulatory.twentyFourHourSystolicMmHg", "bp.ambulatory.total24hSystolicMmHg", "halt.24h.systolic"),
        "halt_24h_diastolic": ("bp.ambulatory24h.diastolicMmHg", "bp.ambulatory.twentyFourHourDiastolicMmHg", "bp.ambulatory.total24hDiastolicMmHg", "halt.24h.diastolic"),
    },
    "bp_thresholds_targets": {
        "HATT": ("bp.officeVisit.systolicMmHg", "bp.systolicMmHg", "bp.systolic"),
        "HATTr": ("bp.officeVisit.diastolicMmHg", "bp.diastolicMmHg", "bp.diastolic"),
        "target_HATT": "target.systolicMmHg",
        "target_HATTr": "target.diastolicMmHg",
        "BĐM": ("comorbidity.cardiovascularDiseaseOrDiabetesOrCkd", "target.organDamagePresent", "comorbidity.associatedConditionPresent", "comorbidity.anyComorbidityPresent", "patient.comorbidityPresent", "comorbidity.targetOrganDamage"),
        "BTMXV": ("risk.highOrCvdOrDiabetesOrCkd", "condition.atheroscleroticCardiovascularDisease", "comorbidity.atheroscleroticCvd", "comorbidity.cardiovascularDisease", "comorbidity.cvdPresent"),
        "ĐTĐ": ("risk.highOrCvdOrDiabetesOrCkd", "condition.diabetesMellitus", "comorbidity.diabetes", "comorbidity.diabetesMellitus", "comorbidity.diabetesPresent"),
        "BTM": ("risk.highOrCvdOrDiabetesOrCkd", "condition.chronicKidneyDisease", "comorbidity.chronicKidneyDisease", "comorbidity.kidneyDiseasePresent"),
        "HIGH_RISK": "risk.highOrCvdOrDiabetesOrCkd",
    },
    "optimized_hypertension_treatment": {
        "office_bp_systolic": ("bp.officeVisit.systolicMmHg", "bp.systolicMmHg"),
        "office_bp_diastolic": ("bp.officeVisit.diastolicMmHg", "bp.diastolicMmHg"),
        "bp_systolic": ("vitals.bp.clinicSystolicMmHg", "bp.officeVisit.systolicMmHg", "bp.systolicMmHg", "bp.systolic"),
        "bp_diastolic": ("vitals.bp.clinicDiastolicMmHg", "bp.officeVisit.diastolicMmHg", "bp.diastolicMmHg", "bp.diastolic"),
        "clinic_bp_systolic": ("vitals.bp.clinicSystolicMmHg", "bp.officeVisit.systolicMmHg", "bp.systolicMmHg", "bp.systolic"),
        "clinic_bp_diastolic": ("vitals.bp.clinicDiastolicMmHg", "bp.officeVisit.diastolicMmHg", "bp.diastolicMmHg", "bp.diastolic"),
        "systolic_bp": ("bp.systolicMmHg", "bp.systolic"),
        "diastolic_bp": ("bp.diastolicMmHg", "bp.diastolic"),
        "ha_tam_thu": ("vitals.bp.clinicSystolicMmHg", "bp.officeVisit.systolicMmHg", "bp.systolicMmHg", "bp.systolic"),
        "ha_tam_truong": ("vitals.bp.clinicDiastolicMmHg", "bp.officeVisit.diastolicMmHg", "bp.diastolicMmHg", "bp.diastolic"),
        "bp_category": ("hypertension.category", "bp.category"),
        "blood_pressure_category": ("hypertension.category", "bp.category"),
        "tinh_trang_ha": ("hypertension.category", "bp.category"),
        "age": ("patient.age", "patient.ageOver65"),
        "hypertension_category": ("hypertension.category", "bp.category"),
        "risk_level": "risk.level",
        "nguy_co": "risk.level",
        "frailty_syndrome": ("patient.frailtySyndrome", "patient.geriatricSyndrome"),
        "geriatric_syndrome": ("patient.frailtySyndrome", "patient.geriatricSyndrome"),
        "bkmxv_present": ("comorbidity.atheroscleroticCardiovascularDisease", "comorbidity.hasCvd"),
        "has_cvd": ("comorbidity.atheroscleroticCardiovascularDisease", "comorbidity.hasCvd", "comorbidity.cardiovascularDisease", "comorbidity.cvdPresent", "patient.hasCvd", "has.cvd"),
        "has_BTMXV": ("comorbidity.atheroscleroticCardiovascularDisease", "comorbidity.hasCvd", "risk.highOrCvdOrDiabetesOrCkd"),
        "has_btmxv": ("comorbidity.atheroscleroticCvDisease", "comorbidity.atheroscleroticCardiovascularDisease", "comorbidity.hasCvd"),
        "ckd_present": ("comorbidity.chronicKidneyDisease", "comorbidity.hasCkd"),
        "has_ckd": ("comorbidity.chronicKidneyDisease", "comorbidity.hasCkd", "comorbidity.kidneyDiseasePresent", "patient.hasCkd"),
        "has_BTM": ("comorbidity.chronicKidneyDisease", "comorbidity.hasCkd"),
        "has_btm": ("comorbidity.kidneyDisease", "comorbidity.chronicKidneyDisease", "comorbidity.hasCkd"),
        "diabetes_present": ("comorbidity.diabetes", "comorbidity.hasDiabetes"),
        "has_diabetes": ("comorbidity.diabetes", "comorbidity.hasDiabetes", "comorbidity.diabetesPresent", "patient.hasDiabetes", "has.diabetes"),
        "has_DTD": ("comorbidity.diabetes", "comorbidity.hasDiabetes"),
        "has_dtd": ("comorbidity.diabetes", "comorbidity.hasDiabetes"),
        "consider_monotherapy_exception": ("treatment.considerMonotherapyException", "treatment.monotherapyException"),
        "lifestyle_duration_months": "lifestyle.durationMonths",
        "treatment_step": "treatment.step",
        "resistant_hypertension": ("treatment.resistantHypertension", "hypertension.resistantHypertension", "hypertension.resistant", "bp.resistantHypertension"),
        "tha_khang_tri": ("treatment.resistantHypertension", "hypertension.resistantHypertension", "hypertension.resistant", "bp.resistantHypertension"),
        "resistant_hypertension_uncontrolled": ("treatment.resistantHypertensionUncontrolled", "hypertension.resistantHypertensionUncontrolled"),
        "compelling_indication": ("treatment.compellingIndication", "treatment.compulsoryIndication", "clinical.compulsoryIndication", "patient.compulsoryIndication"),
        "compulsory_indication": ("treatment.compellingIndication", "treatment.compulsoryIndication", "clinical.compulsoryIndication", "patient.compulsoryIndication", "condition.compulsoryIndication"),
        "additional_medication": ("treatment.additionalMedication", "medication.additionalMedication"),
        "blood_pressure_controlled": ("treatment.bloodPressureControlled", "hypertension.bloodPressureControlled", "bp.controlled"),
        "chua_dat_muc_tieu": ("treatment.bloodPressureControlled", "hypertension.bloodPressureControlled", "bp.controlled", "treatment.hypertensionControlled", "treatment.targetAchieved", "treatment.resistantHypertensionUncontrolled"),
        "chi_dinh_bat_buoc": ("treatment.compulsoryIndication", "treatment.compellingIndication", "clinical.compulsoryIndication", "patient.compulsoryIndication"),
    },
    "hypertension_risk_stratification": {
        "HATT": ("bp.systolicMmHg", "bp.systolic", "hATT"),
        "HATTr": ("bp.diastolicMmHg", "bp.diastolic", "hATTr"),
        "YTNC_count": ("risk.cardiovascularRiskFactorCount", "risk.ytncCount", "risk.cardiovascularRiskCount", "yTNC.count"),
        "has_TOD_CVD_DM": ("target.organDamageOrCvdOrDiabetes", "condition.hasTodCvdDm", "target.todCvdDmPresent", "has.TOD.CVD.DM", "risk.hasTodCvdDm"),
        "age": ("patient.age", "patient.ageOver65", "risk.age"),
        "gender": ("patient.gender", "patient.genderMale", "risk.gender"),
        "heart_rate": ("vitals.heartRate", "vitals.heartRateBpm", "risk.heartRate"),
        "overweight": ("patient.overweight", "condition.overweight", "comorbidity.overweight", "patient.overweightPresent", "risk.overweight"),
        "diabetes": ("comorbidity.diabetes", "condition.diabetesMellitus", "patient.diabetesPresent", "comorbidity.diabetesPresent", "patient.diabetes", "risk.diabetes"),
        "LDL_C": ("laboratory.ldlCholesterol", "laboratory.ldlCholesterolHigh", "laboratory.ldlCholesterolLevel", "laboratory.ldlC", "risk.ldlC"),
        "ldl": ("laboratory.ldlCholesterol", "laboratory.ldlCholesterolHigh", "laboratory.ldlCholesterolLevel", "laboratory.ldlC", "risk.ldlC"),
        "triglyceride": ("laboratory.triglyceride", "laboratory.triglycerideHigh", "laboratory.triglycerideLevel", "laboratory.triglyceride", "risk.triglyceride"),
        "family_history_cvd": ("patient.familyHistoryCvd", "familyHistory.cardiovascularDisease", "family.cvdHistory", "patient.familyHistoryCvd", "risk.familyCvd"),
        "family_cvd": ("patient.familyHistoryCvd", "familyHistory.cardiovascularDisease", "family.cvdHistory", "risk.familyCvd"),
        "family_history_hypertension": ("patient.familyHistoryHypertension", "familyHistory.hypertension", "family.hypertensionHistory", "patient.familyHistoryHypertension", "risk.familyHypertension"),
        "early_menopause": "patient.earlyMenopause",
        "smoking": ("patient.smoking", "lifestyle.smoking", "social.smoking", "patient.smokingPresent", "risk.smoking"),
        "socioeconomic_risk_factors": ("patient.socioeconomicRiskFactors", "social.riskFactors", "social.socioeconomicRiskFactors", "patient.socioeconomicRiskPresent", "risk.socioeconomic"),
        "socioeconomic": ("patient.socioeconomicRiskFactors", "social.riskFactors", "social.socioeconomicRiskFactors", "patient.socioeconomicRiskPresent", "risk.socioeconomic"),
        "LVH_ECG": ("target.leftVentricularHypertrophyEcg", "condition.lvhEcg", "cardiac.lvhEcg", "risk.lvhEcg"),
        "eGFR": ("laboratory.eGfr", "laboratory.egfr", "laboratory.egfrValue", "risk.egfr"),
        "other_TOD": ("target.otherOrganDamage", "condition.otherTod", "comorbidity.otherTod", "target.otherOrganDamagePresent", "patient.otherTod", "risk.otherTod"),
        "other_tod": ("target.otherOrganDamage", "condition.otherTod", "comorbidity.otherTod", "target.otherOrganDamagePresent", "patient.otherTod", "risk.otherTod"),
        "coronary_heart_disease": ("comorbidity.coronaryHeartDisease", "condition.coronaryHeartDisease", "comorbidity.coronaryHeartDiseasePresent", "patient.coronaryHeartDisease", "risk.coronaryHeartDisease"),
        "heart_failure": ("comorbidity.heartFailure", "condition.heartFailure", "comorbidity.heartFailurePresent", "patient.heartFailure", "risk.heartFailure"),
        "stroke": ("comorbidity.stroke", "condition.stroke", "comorbidity.strokePresent", "patient.stroke", "risk.stroke"),
        "peripheral_artery_disease": ("comorbidity.peripheralArteryDisease", "condition.peripheralArteryDisease", "comorbidity.peripheralArteryDiseasePresent", "patient.peripheralArteryDisease", "risk.peripheralArteryDisease"),
        "atrial_fibrillation": ("comorbidity.atrialFibrillation", "condition.atrialFibrillation", "comorbidity.atrialFibrillationPresent", "patient.atrialFibrillation", "risk.atrialFibrillation"),
        "ckd_stage": ("comorbidity.ckdStage", "condition.chronicKidneyDiseaseStage", "comorbidity.chronicKidneyDiseaseStage", "patient.ckdStage", "risk.ckdStage"),
    },
    "uncontrolled_resistant_hypertension": {
        "seated_sbp": ("bp.seatedSystolicMmHg", "bp.seated.systolicMmHg", "seated.sbp"),
        "regimen_stable_weeks": ("treatment.regimenStableWeeks", "regimen.stable.weeks"),
        "antihypertensive_agents_count": ("treatment.antihypertensiveAgentsCount", "medication.antihypertensiveAgentsCount", "antihypertensive.agents.count"),
        "includes_diuretic": ("treatment.includesDiuretic", "medication.includesDiuretic", "includes.diuretic"),
        "eGFR": ("laboratory.eGfr", "laboratory.egfr", "laboratory.egfrValue", "eGFR", "lab.eGFR"),
        "K+": ("laboratory.potassium", "laboratory.potassiumMmolL", "laboratory.potassiumLevel", "k", "lab.potassium"),
        "Na+": ("laboratory.sodium", "laboratory.sodiumMmolL", "laboratory.sodiumLevel", "na", "lab.sodium"),
        "pregnancy": ("patient.pregnancy", "patient.pregnancyStatus", "pregnancy"),
        "liver": ("laboratory.liverFunctionNormal", "laboratory.liverAbnormalities", "laboratory.liverStatus", "laboratory.liverFunction", "laboratory.liver", "liver", "comorbidity.liverDisease"),
        "sbp_decrease_12_wks_mmhg": ("bp.sbpDecrease12WeeksMmHg", "bp.sbpDecrease12WksMmHg", "sbp.decrease.12.wks.mmhg"),
    },
}

COMPOSITE_BP_ALIASES = {
    "ha_pk_1": ("ha_pk_1_systolic", "ha_pk_1_diastolic"),
}


def evidence_variable_id(tree_id: str, raw_id: Any, known_ids: set[str]) -> str | None:
    if not isinstance(raw_id, str):
        return None
    if raw_id in known_ids:
        return raw_id
    aliases = EVIDENCE_VARIABLE_ALIASES.get(tree_id, {})
    alias = aliases.get(raw_id)
    if alias is None:
        alias = next((candidate for name, candidate in aliases.items() if name.lower() == raw_id.lower()), None)
    candidates = alias if isinstance(alias, tuple) else (alias,)
    for candidate in candidates:
        if candidate in known_ids:
            return candidate
    lowered = {item.lower(): item for item in known_ids}
    return lowered.get(raw_id.lower())


def canonical_evidence_value(value: Any, variable_id: str | None, variable_map: dict[str, dict[str, Any]]) -> Any:
    variable = variable_map.get(variable_id or "", {})
    data_type = variable.get("dataType")
    if isinstance(value, list):
        return [canonical_evidence_value(item, variable_id, variable_map) for item in value]
    if data_type in {"number", "integer"} and isinstance(value, str):
        try:
            return int(value) if data_type == "integer" else float(value)
        except ValueError:
            return value
    return value


def canonical_evidence_leaf(tree_id: str, raw_id: Any, operator: str, value: Any, bundle: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(raw_id, dict):
        raw_id = raw_id.get("v") or raw_id.get("var") or raw_id.get("field")
    if not isinstance(raw_id, str):
        return None
    known_ids = {item.get("id") for item in bundle.get("variables", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}
    variable_map = {item.get("id"): item for item in bundle.get("variables", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}
    composite = COMPOSITE_BP_ALIASES.get(raw_id)
    if composite and isinstance(value, str) and re.fullmatch(r"\s*\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?\s*", value):
        systolic, diastolic = [float(item.strip()) for item in value.split("/", 1)]
        systolic = int(systolic) if systolic.is_integer() else systolic
        diastolic = int(diastolic) if diastolic.is_integer() else diastolic
        first = canonical_evidence_leaf(tree_id, composite[0], operator, systolic, bundle)
        second = canonical_evidence_leaf(tree_id, composite[1], operator, diastolic, bundle)
        return {"all": [first, second]} if first and second else None
    resolved = evidence_variable_id(tree_id, raw_id, known_ids)
    if not resolved:
        return None
    operator_text = str(operator).strip()
    if operator_text.endswith("v") and operator_text[:-1] in {"==", "=", ">", ">=", "<", "<=", "in", "IN"}:
        operator_text = operator_text[:-1]
    normalized_operator = {"==": "eq", "=": "eq", ">": "gt", ">=": "gte", "<": "lt", "<=": "lte", "in": "in", "IN": "in", "exists": "present", "present": "present"}.get(operator_text, operator_text.lower())
    result = {"field": resolved, "op": normalized_operator}
    if normalized_operator != "present":
        result["value"] = canonical_evidence_value(value, resolved, variable_map)
    return result


def canonicalize_evidence_predicate(value: Any, tree_id: str, bundle: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return canonical_evidence_leaf(tree_id, value, "eq", True, bundle) or value
    if not isinstance(value, dict):
        return value
    if "field" in value and "op" in value:
        return canonical_evidence_leaf(tree_id, value.get("field"), value.get("op"), value.get("value"), bundle) or value
    if "all" in value or "any" in value:
        key = "all" if "all" in value else "any"
        return {key: [canonicalize_evidence_predicate(item, tree_id, bundle) for item in value[key]]}
    for mongo_operator, key in (("$or", "any"), ("$and", "all")):
        if isinstance(value.get(mongo_operator), list):
            return {key: [canonicalize_evidence_predicate(item, tree_id, bundle) for item in value[mongo_operator]]}
    # Normalize simple Mongo-style evidence such as
    # {"seated_sbp":{"$gte":140,"$lte":169}}.
    predicate_operators = {"and", "or", "between", "betweenv", "==", "=", ">", ">=", "<", "<=", "in", "IN", "==v", ">v", ">=v", "<v", "<=v", "inv"}
    mongo_fields = [(field, condition) for field, condition in value.items() if field not in predicate_operators and not str(field).startswith("$")]
    if len(mongo_fields) == 1:
        field, condition = mongo_fields[0]
        if isinstance(condition, dict):
            leaves: list[dict[str, Any]] = []
            for mongo_operator, comparison_value in condition.items():
                operator_map = {"$eq": "eq", "$gte": "gte", "$gt": "gt", "$lte": "lte", "$lt": "lt", "$in": "in", "$exists": "present"}
                canonical_operator = operator_map.get(mongo_operator)
                if canonical_operator is None:
                    continue
                if canonical_operator == "present":
                    leaf = canonical_evidence_leaf(tree_id, field, "present", None, bundle)
                else:
                    leaf = canonical_evidence_leaf(tree_id, field, canonical_operator, comparison_value, bundle)
                if leaf:
                    leaves.append(leaf)
            if leaves:
                return leaves[0] if len(leaves) == 1 else {"all": leaves}
        else:
            return canonical_evidence_leaf(tree_id, field, "eq", condition, bundle) or value
    operator = value.get("operator")
    if isinstance(value.get("conditions"), list):
        if str(operator).lower() in {"and", "all"}:
            return {"all": [canonicalize_evidence_predicate(item, tree_id, bundle) for item in value["conditions"]]}
        if str(operator).lower() in {"or", "any"}:
            return {"any": [canonicalize_evidence_predicate(item, tree_id, bundle) for item in value["conditions"]]}
        if len(value["conditions"]) == 1 and isinstance(value["conditions"][0], dict):
            child = dict(value["conditions"][0])
            child.setdefault("operator", operator)
            if "value" not in child and "variable_comparison" in child:
                child["value"] = child["variable_comparison"]
            return canonicalize_evidence_predicate(child, tree_id, bundle)
        if isinstance(value.get("variable"), str):
            comparison_value = value.get("value", value.get("variable_comparison"))
            return canonical_evidence_leaf(tree_id, value["variable"], str(operator), comparison_value, bundle) or value
    if isinstance(value.get("variable"), str):
        raw_operator = str(operator or "present")
        if raw_operator.lower() == "between":
            bounds = value.get("value") or [value.get("low"), value.get("high")]
            if isinstance(bounds, list) and len(bounds) == 2:
                lower = canonical_evidence_leaf(tree_id, value["variable"], "gte", bounds[0], bundle)
                upper = canonical_evidence_leaf(tree_id, value["variable"], "lte", bounds[1], bundle)
                return {"all": [lower, upper]} if lower and upper else value
        return canonical_evidence_leaf(tree_id, value["variable"], raw_operator, value.get("value"), bundle) or value
    for raw_operator, args in value.items():
        raw_operator = raw_operator.strip() if isinstance(raw_operator, str) else raw_operator
        if raw_operator in {"and", "or"} and isinstance(args, list):
            return {"all" if raw_operator == "and" else "any": [canonicalize_evidence_predicate(item, tree_id, bundle) for item in args]}
        if raw_operator in {"between", "betweenv"} and isinstance(args, list) and len(args) == 3:
            lower = canonical_evidence_leaf(tree_id, args[0], "gte", args[1], bundle)
            upper = canonical_evidence_leaf(tree_id, args[0], "lte", args[2], bundle)
            return {"all": [lower, upper]} if lower and upper else value
        if raw_operator in {"==", "=", ">", ">=", "<", "<=", "in", "IN", "==v", ">v", ">=v", "<v", "<=v", "inv"} and isinstance(args, list) and len(args) >= 2:
            raw_id = args[0]
            comparison_value = args[1]
            if raw_operator in {"in", "IN", "inv"} and isinstance(args[1], dict):
                raw_id = args[1]
                comparison_value = [args[0]]
            return canonical_evidence_leaf(tree_id, raw_id, raw_operator, comparison_value, bundle) or value
    return value


def canonicalize_evidence_claims(evidence: dict[str, Any], tree_id: str, bundle: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(evidence)) if isinstance(evidence, dict) else evidence
    if not isinstance(normalized, dict):
        return normalized
    known_ids = {item.get("id") for item in bundle.get("variables", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}
    for claim in normalized.get("claims", []) if isinstance(normalized.get("claims"), list) else []:
        if not isinstance(claim, dict):
            continue
        raw_variables = decode_json_value(claim.get("variablesJson"), [])
        if isinstance(raw_variables, dict):
            raw_ids = list(raw_variables.keys())
        elif isinstance(raw_variables, list):
            raw_ids = [
                item if isinstance(item, str) else item.get("name")
                for item in raw_variables
                if isinstance(item, str) or isinstance(item, dict) and isinstance(item.get("name"), str)
            ]
        else:
            raw_ids = []
        mapped_ids: list[str] = []
        for raw_id in raw_ids:
            composite = COMPOSITE_BP_ALIASES.get(raw_id)
            if composite:
                mapped_ids.extend(item for item in composite if evidence_variable_id(tree_id, item, known_ids))
            else:
                mapped = evidence_variable_id(tree_id, raw_id, known_ids)
                # Preserve an unresolved source label so the strict verifier
                # can report it as a real coverage error; never hide evidence
                # by silently dropping an unmapped identifier.
                mapped_ids.append(mapped or raw_id)
        claim["variablesJson"] = json.dumps(sorted(set(mapped_ids)), ensure_ascii=False)
        predicate = decode_json_value(claim.get("predicateJson"), None)
        if predicate is not None:
            claim["predicateJson"] = json.dumps(canonicalize_evidence_predicate(predicate, tree_id, bundle), ensure_ascii=False)
    return normalized


def evidence_predicate_variables(value: Any) -> set[str]:
    """Collect variable references from every supported evidence predicate shape."""
    found: set[str] = set()
    if not isinstance(value, dict):
        return found
    for key in ("field", "variable"):
        if isinstance(value.get(key), str):
            found.add(value[key])
    for key in ("all", "any", "conditions"):
        items = value.get(key)
        if isinstance(items, list):
            for item in items:
                found.update(evidence_predicate_variables(item))
    for operator, args in value.items():
        operator = operator.strip() if isinstance(operator, str) else operator
        if operator in {"and", "or"} and isinstance(args, list):
            for item in args:
                found.update(evidence_predicate_variables(item))
        elif operator in {"between", "==", "=", ">", ">=", "<", "<=", "in", "IN", "==v", "=v", ">v", ">=v", "<v", "<=v", "inv"} and isinstance(args, list):
            if args and isinstance(args[0], dict):
                found.update(evidence_predicate_variables(args[0]))
            elif len(args) > 1 and isinstance(args[1], dict):
                found.update(evidence_predicate_variables(args[1]))
            elif args and isinstance(args[0], str):
                found.add(args[0])
    return found


def evidence_variable_reference_errors(evidence: dict[str, Any], bundle: dict[str, Any]) -> list[str]:
    """Fail closed when canonical evidence still references an undeclared field."""
    known_ids = {
        item.get("id")
        for item in bundle.get("variables", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    errors: list[str] = []
    claims = evidence.get("claims") if isinstance(evidence, dict) else None
    if not isinstance(claims, list):
        return ["evidence claims must be an array"]
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            errors.append(f"evidence claims[{index}] must be an object")
            continue
        claim_id = claim.get("claimId", index)
        raw_variables = decode_json_value(claim.get("variablesJson"), None)
        references: set[str] = set()
        if isinstance(raw_variables, dict):
            references.update(key for key in raw_variables if isinstance(key, str))
        elif isinstance(raw_variables, list):
            references.update(item for item in raw_variables if isinstance(item, str))
        elif raw_variables is None:
            errors.append(f"evidence claim {claim_id}: variablesJson is invalid")
        predicate = decode_json_value(claim.get("predicateJson"), None)
        if predicate is None:
            errors.append(f"evidence claim {claim_id}: predicateJson is invalid")
        else:
            references.update(evidence_predicate_variables(predicate))
        unresolved = sorted(reference for reference in references if reference not in known_ids and not reference.startswith(":"))
        errors.extend(f"evidence claim {claim_id}: unresolved variable {reference}" for reference in unresolved)
    return errors


def canonicalize_variable_proposal(proposal: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalize identifier syntax before merge, while preserving an audit trail."""
    normalized_proposal = json.loads(json.dumps(proposal))
    values = decode_json_value(normalized_proposal.get("variablesJson"), None)
    if not isinstance(values, list):
        return normalized_proposal, []
    changes: list[str] = []
    for variable in values:
        if not isinstance(variable, dict) or not isinstance(variable.get("id"), str):
            continue
        canonical_id, change = canonical_variable_id(variable["id"])
        if canonical_id and change:
            changes.append(change)
            variable["id"] = canonical_id
        derived = variable.get("derivedFrom")
        if isinstance(derived, str):
            derived = decode_json_value(derived, [])
        if isinstance(derived, list):
            canonical_derived: list[Any] = []
            for item in derived:
                if isinstance(item, str):
                    canonical_item, derived_change = canonical_variable_id(item)
                    if canonical_item:
                        canonical_derived.append(canonical_item)
                        if derived_change:
                            changes.append(derived_change)
                    else:
                        canonical_derived.append(item)
                else:
                    canonical_derived.append(item)
            variable["derivedFrom"] = canonical_derived
    normalized_proposal["variablesJson"] = values
    return normalized_proposal, changes


def canonical_source_ref(raw_ref: Any, source_documents: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    """Normalize a model source reference against the manifest source catalog."""
    source_id = raw_ref if isinstance(raw_ref, str) else raw_ref.get("sourceId") if isinstance(raw_ref, dict) else None
    document = source_documents.get(source_id)
    if not isinstance(document, dict):
        return None, f"invalid sourceId {source_id!r}"
    filename = Path(str(document.get("localFile", ""))).name
    ref = dict(raw_ref) if isinstance(raw_ref, dict) else {}
    ref["sourceId"] = source_id
    page = ref.get("page", 1)
    if isinstance(page, str) and page.isdigit():
        page = int(page)
    # Gemini may use zero-based indexing for an attached image. The manifest
    # exposes the image as page 1, so this is a deterministic transport repair.
    if page == 0:
        page = 1
    ref["page"] = page
    ref.setdefault("section", document.get("title", "Evidence"))
    # The sourceId -> image filename mapping is authoritative. This repairs a
    # harmless provider formatting error without changing provenance.
    ref["tableOrFigure"] = filename
    ref.setdefault("note", "Evidence reference supplied by the extraction agent.")
    return ref, None


def merge_variable_proposal(
    bundle: dict[str, Any],
    proposal: dict[str, Any],
    replace_ids: set[str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Add well-formed new variables to the draft working catalog.

    The agent schema transports nested arrays as JSON strings for provider
    compatibility. Decode those fields here and reject malformed proposals;
    never silently turn a missing source reference into a valid variable.
    """
    working = json.loads(json.dumps(bundle))
    errors: list[str] = []
    if proposal.get("status") in {"agent_error", "validation_error", "pipeline_error"}:
        return working, [proposal.get("code", "variable_agent_failed")]
    proposed = decode_json_value(proposal.get("variablesJson"), None)
    if proposed is None:
        return working, ["variablesJson is not valid JSON"]
    if not isinstance(proposed, list):
        return working, ["variablesJson must decode to an array"]

    existing = {item["id"]: item for item in working.get("variables", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}
    existing_indexes = {
        item.get("id"): index
        for index, item in enumerate(working.get("variables", []))
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    source_documents = {
        item.get("id"): item
        for item in working.get("sourceDocuments", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    source_ids = set(source_documents)
    for index, raw in enumerate(proposed):
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"]:
            errors.append(f"variablesJson[{index}] requires a non-empty id")
            continue
        variable = dict(raw)
        for encoded_key, canonical_key, fallback in (
            ("sourceRefsJson", "sourceRefs", None),
            ("derivedFromJson", "derivedFrom", []),
        ):
            if encoded_key in variable:
                decoded = decode_json_value(variable.get(encoded_key), fallback)
                if decoded is None:
                    errors.append(f"{variable['id']}: {encoded_key} is not valid JSON")
                    continue
                variable[canonical_key] = decoded
                variable.pop(encoded_key, None)
        variable.setdefault("requiredForEvaluation", False)
        variable.setdefault("unit", None)
        if not isinstance(variable.get("label"), str) or not variable["label"].strip():
            errors.append(f"{variable['id']}: label is required")
            continue
        if not isinstance(variable.get("definition"), str) or not variable["definition"].strip():
            errors.append(f"{variable['id']}: definition is required")
            continue
        if not isinstance(variable.get("sourceSystem"), str) or not variable["sourceSystem"].strip():
            errors.append(f"{variable['id']}: sourceSystem is required")
            continue
        if variable.get("sourceSystem") not in CANONICAL_SOURCE_SYSTEMS:
            errors.append(f"{variable['id']}: invalid sourceSystem {variable.get('sourceSystem')!r}")
            continue
        if not re.fullmatch(r"[a-z][a-zA-Z0-9]*(\.[a-zA-Z0-9_]+)*", variable["id"]):
            errors.append(f"{variable['id']}: id does not match canonical variable ID syntax")
            continue
        if variable.get("dataType") not in {"boolean", "integer", "number", "string", "enum"}:
            errors.append(f"{variable['id']}: invalid dataType")
            continue
        if variable.get("dataType") == "enum" and (not isinstance(variable.get("allowedValues"), list) or not variable["allowedValues"]):
            errors.append(f"{variable['id']}: enum variables require allowedValues")
            continue
        raw_refs = variable.get("sourceRefs")
        if not isinstance(raw_refs, list) or not raw_refs:
            errors.append(f"{variable['id']}: sourceRefs must be a non-empty array")
            continue
        canonical_refs: list[dict[str, Any]] = []
        invalid_ref = False
        for ref_index, raw_ref in enumerate(raw_refs):
            ref, ref_error = canonical_source_ref(raw_ref, source_documents)
            if ref_error or ref is None:
                errors.append(f"{variable['id']}.sourceRefs[{ref_index}]: {ref_error or 'invalid reference'}")
                invalid_ref = True
                continue
            page = ref.get("page")
            if isinstance(page, bool) or not isinstance(page, int) or page < 1:
                errors.append(f"{variable['id']}.sourceRefs[{ref_index}]: page must be a positive integer")
                invalid_ref = True
            for key in ("section", "tableOrFigure", "note"):
                if not isinstance(ref.get(key), str) or not ref[key].strip():
                    errors.append(f"{variable['id']}.sourceRefs[{ref_index}]: {key} is required")
                    invalid_ref = True
            canonical_refs.append(ref)
        variable["sourceRefs"] = canonical_refs
        if variable["id"] in existing and variable["id"] not in (replace_ids or set()):
            current = existing[variable["id"]]
            for key in ("dataType", "sourceSystem", "allowedValues"):
                if key in variable and current.get(key) != variable.get(key):
                    errors.append(
                        f"{variable['id']}: conflicts with existing shared definition for {key}"
                    )
            continue
        if invalid_ref:
            continue
        existing[variable["id"]] = variable
        if variable["id"] in existing_indexes:
            working["variables"][existing_indexes[variable["id"]]] = variable
        else:
            existing_indexes[variable["id"]] = len(working["variables"])
            working["variables"].append(variable)
    return working, errors


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generate_or_error(client: GeminiClient, role: str, prompt: str, schema: dict[str, Any], image_paths: list[Path] | None = None) -> dict[str, Any]:
    try:
        return client.generate_json(role, prompt, schema, image_paths=image_paths)
    except Exception as exc:
        return safe_error(exc)


def normalise_or_error(draft: dict[str, Any], expected_tree_id: str | None = None) -> dict[str, Any]:
    if draft.get("status") in {"agent_error", "validation_error", "pipeline_error"}:
        return draft
    try:
        return normalise_tree(draft)
    except Exception as exc:
        error = safe_error(exc)
        if expected_tree_id:
            error["id"] = expected_tree_id
        return error


def has_agent_failure(payload: Any) -> bool:
    if isinstance(payload, dict):
        if payload.get("status") in {"agent_error", "validation_error", "pipeline_error"}:
            return True
        return any(has_agent_failure(value) for value in payload.values())
    if isinstance(payload, list):
        return any(has_agent_failure(value) for value in payload)
    return False


def evidence_pages_for_tree(tree_id: str, bundle: dict[str, Any]) -> set[int]:
    """Allow a tree to cite the pages in its own and linked evidence refs."""
    pages: set[int] = set()
    tree_map = {
        item.get("id"): item
        for item in bundle.get("trees", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    visited: set[str] = set()

    def visit(current_tree_id: str) -> None:
        if current_tree_id in visited:
            return
        visited.add(current_tree_id)
        current = tree_map.get(current_tree_id)
        if not isinstance(current, dict):
            return
        for source_ref in current.get("sourceRefs", []):
            page = source_ref.get("page") if isinstance(source_ref, dict) else None
            if isinstance(page, int) and not isinstance(page, bool):
                pages.add(page)
        for node in current.get("nodes", []):
            if isinstance(node, dict) and node.get("type") == "link" and isinstance(node.get("data"), dict):
                target = node["data"].get("targetTreeId")
                if isinstance(target, str):
                    visit(target)

    visit(tree_id)
    return pages


def source_ids_for_tree(tree_id: str, bundle: dict[str, Any]) -> set[str]:
    """Return only sources belonging to the target tree and its linked trees."""
    tree_map = {
        item.get("id"): item
        for item in bundle.get("trees", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    source_ids: set[str] = set()
    visited: set[str] = set()

    def visit(current_tree_id: str) -> None:
        if current_tree_id in visited:
            return
        visited.add(current_tree_id)
        current = tree_map.get(current_tree_id)
        if not isinstance(current, dict):
            return
        for ref in current.get("sourceRefs", []):
            if isinstance(ref, dict) and isinstance(ref.get("sourceId"), str):
                source_ids.add(ref["sourceId"])
        for node_item in current.get("nodes", []):
            if not isinstance(node_item, dict):
                continue
            for ref in node_item.get("sourceRefs", []):
                if isinstance(ref, dict) and isinstance(ref.get("sourceId"), str):
                    source_ids.add(ref["sourceId"])
            data = node_item.get("data")
            if node_item.get("type") == "link" and isinstance(data, dict) and isinstance(data.get("targetTreeId"), str):
                visit(data["targetTreeId"])

    visit(tree_id)
    return source_ids


def target_provenance_errors(tree_id: str, candidate: dict[str, Any], bundle: dict[str, Any]) -> list[str]:
    """Reject source references copied from another tree or another image."""
    allowed_source_ids = source_ids_for_tree(tree_id, bundle)
    documents = {
        item.get("id"): item
        for item in bundle.get("sourceDocuments", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    errors: list[str] = []
    references: list[tuple[str, Any]] = [("tree.sourceRefs", candidate.get("sourceRefs", []))]
    for node_item in candidate.get("nodes", []) if isinstance(candidate, dict) else []:
        if isinstance(node_item, dict):
            references.append((f"{node_item.get('id', '<unknown>')}.sourceRefs", node_item.get("sourceRefs", [])))
    for path, refs in references:
        if not isinstance(refs, list):
            continue
        for index, source_ref in enumerate(refs):
            if not isinstance(source_ref, dict):
                continue
            source_id = source_ref.get("sourceId")
            if source_id not in allowed_source_ids:
                errors.append(f"{path}[{index}]: sourceId {source_id!r} is outside target evidence")
                continue
            document = documents.get(source_id)
            expected_figure = Path(str(document.get("localFile", ""))).name if isinstance(document, dict) else ""
            if expected_figure and source_ref.get("tableOrFigure") != expected_figure:
                errors.append(f"{path}[{index}]: tableOrFigure does not match sourceId {source_id}")
    return errors


def predicate_fields(value: Any) -> set[str]:
    fields: set[str] = set()
    if isinstance(value, dict):
        if isinstance(value.get("field"), str):
            fields.add(value["field"])
        for child in value.values():
            fields.update(predicate_fields(child))
    elif isinstance(value, list):
        for child in value:
            fields.update(predicate_fields(child))
    return fields


def canonicalize_candidate_source_refs(candidate: dict[str, Any], bundle: dict[str, Any]) -> list[str]:
    """Canonicalize harmless filename formatting errors before strict checks."""
    documents = {
        item.get("id"): item
        for item in bundle.get("sourceDocuments", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    errors: list[str] = []
    references: list[tuple[str, dict[str, Any]]] = [("tree", candidate)]
    references.extend(
        (str(node.get("id", "<unknown>")), node)
        for node in candidate.get("nodes", [])
        if isinstance(node, dict)
    )
    for path, owner in references:
        raw_refs = owner.get("sourceRefs")
        if not isinstance(raw_refs, list):
            continue
        canonical_refs: list[dict[str, Any]] = []
        for index, raw_ref in enumerate(raw_refs):
            ref, ref_error = canonical_source_ref(raw_ref, documents)
            if ref_error or ref is None:
                errors.append(f"{path}.sourceRefs[{index}]: {ref_error or 'invalid reference'}")
            else:
                canonical_refs.append(ref)
        if len(canonical_refs) == len(raw_refs):
            owner["sourceRefs"] = canonical_refs
    return errors


def candidate_validation_errors(tree_id: str, draft: dict[str, Any], bundle: dict[str, Any]) -> list[str]:
    if draft.get("status") in {"agent_error", "validation_error", "pipeline_error"}:
        return [draft.get("code", "agent_error")]
    provenance_normalization_errors = canonicalize_candidate_source_refs(draft, bundle)
    errors = semantic_check(
        draft,
        bundle,
        tree_id,
        evidence_pages=evidence_pages_for_tree(tree_id, bundle),
    )
    declared_inputs = set(draft.get("inputVariables", [])) if isinstance(draft.get("inputVariables"), list) else set()
    for node_item in draft.get("nodes", []) if isinstance(draft, dict) else []:
        if not isinstance(node_item, dict) or node_item.get("type") != "condition":
            continue
        logic = node_item.get("logic")
        if not isinstance(logic, dict):
            continue
        for field in sorted(predicate_fields(logic.get("predicate")) - declared_inputs):
            errors.append(f"{node_item.get('id', '<unknown>')}: predicate references undeclared input variable {field}")
    errors.extend(provenance_normalization_errors)
    errors.extend(target_provenance_errors(tree_id, draft, bundle))
    return errors


def strict_verifier_errors(verifier: dict[str, Any], pass_criteria: dict[str, Any]) -> list[str]:
    """Apply the independent pass file; never trust verifier status alone."""
    errors: list[str] = []
    rules = pass_criteria.get("verifier", {})
    if verifier.get("status") != rules.get("statusExactly", "pass"):
        errors.append(f"verifier status is {verifier.get('status')!r}, expected pass")
    issues = verifier.get("issues")
    if not isinstance(issues, list):
        errors.append("verifier issues must be an array")
    elif rules.get("issuesMustBeEmpty", True) and issues:
        errors.append(f"verifier returned {len(issues)} issue(s)")

    coverage = parse_json_string(verifier.get("coverageJson"), None)
    coverage_rules = rules.get("coverage", {})
    if coverage_rules.get("required", True) and not isinstance(coverage, dict):
        errors.append("coverageJson is missing or invalid")
    elif isinstance(coverage, dict):
        ratio = coverage.get("coverageRatio")
        percentage = coverage.get("coveragePercentage")
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)):
            errors.append("coverageRatio must be numeric")
        elif ratio < coverage_rules.get("minimumCoverageRatio", 1.0):
            errors.append(f"coverageRatio {ratio} is below strict minimum")
        if isinstance(percentage, bool) or not isinstance(percentage, (int, float)):
            errors.append("coveragePercentage must be numeric")
        elif percentage < coverage_rules.get("minimumCoveragePercentage", 100):
            errors.append(f"coveragePercentage {percentage} is below strict minimum")
        uncovered = coverage.get("uncoveredClaims")
        if not isinstance(uncovered, list):
            errors.append("coverageJson.uncoveredClaims must be an array")
        elif coverage_rules.get("uncoveredClaimsMustBeEmpty", True) and uncovered:
            errors.append(f"uncoveredClaims is not empty: {uncovered}")

    missing = parse_json_string(verifier.get("missingDataJson"), None)
    missing_rules = rules.get("missingData", {})
    if not isinstance(missing, dict):
        errors.append("missingDataJson is missing or invalid")
    else:
        missing_variables = missing.get("missingVariables")
        missing_items = missing.get("missingItems")
        if not isinstance(missing_variables, list):
            errors.append("missingDataJson.missingVariables must be an array")
        elif missing_rules.get("missingVariablesMustBeEmpty", True) and missing_variables:
            errors.append(f"missingVariables is not empty: {missing_variables}")
        if not isinstance(missing_items, list):
            errors.append("missingDataJson.missingItems must be an array")
        elif missing_rules.get("missingItemsMustBeEmpty", True) and missing_items:
            errors.append(f"missingItems is not empty: {missing_items}")
    return errors


def strict_variable_verifier_errors(verifier: dict[str, Any]) -> list[str]:
    """Apply the variable-stage pass gate independently from tree verification."""
    if not isinstance(verifier, dict):
        return ["variable verifier report is missing or invalid"]
    errors: list[str] = []
    if verifier.get("status") != "pass":
        errors.append(f"variable verifier status is {verifier.get('status')!r}, expected pass")
    issues = verifier.get("issues")
    if not isinstance(issues, list):
        errors.append("variable verifier issues must be an array")
    elif issues:
        errors.append(f"variable verifier returned {len(issues)} issue(s)")

    coverage = parse_json_string(verifier.get("coverageJson"), None)
    if not isinstance(coverage, dict):
        errors.append("variable coverageJson is missing or invalid")
    else:
        ratio = coverage.get("coverageRatio")
        percentage = coverage.get("coveragePercentage")
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or ratio < 1.0:
            errors.append(f"variable coverageRatio {ratio!r} is below strict minimum")
        if isinstance(percentage, bool) or not isinstance(percentage, (int, float)) or percentage < 100:
            errors.append(f"variable coveragePercentage {percentage!r} is below strict minimum")
        if not isinstance(coverage.get("uncoveredClaims"), list):
            errors.append("variable coverageJson.uncoveredClaims must be an array")
        elif coverage["uncoveredClaims"]:
            errors.append(f"variable uncoveredClaims is not empty: {coverage['uncoveredClaims']}")

    for field in ("missingVariablesJson", "invalidVariablesJson"):
        values = parse_json_string(verifier.get(field), None)
        if not isinstance(values, list):
            errors.append(f"{field} must decode to an array")
        elif values:
            errors.append(f"{field} is not empty: {values}")
    return errors


def normalize_variable_verification(verifier: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalize provider scalar zero for an empty coverage list.

    Gemini sometimes serializes an empty ``uncoveredClaims`` array as ``0``
    while still returning coverage 100%. This changes only the transport shape;
    any non-zero scalar remains invalid and is sent back to the repair loop.
    """
    normalized = json.loads(json.dumps(verifier)) if isinstance(verifier, dict) else verifier
    changes: list[str] = []
    if not isinstance(normalized, dict):
        return normalized, changes
    coverage = parse_json_string(normalized.get("coverageJson"), None)
    if isinstance(coverage, dict) and coverage.get("uncoveredClaims") == 0:
        coverage["uncoveredClaims"] = []
        normalized["coverageJson"] = json.dumps(coverage, ensure_ascii=False)
        changes.append("coverageJson.uncoveredClaims: 0 -> []")
    return normalized, changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=EXTRACTION_MANIFEST_PATH, help="Evidence manifest identifying the input images and requested trees")
    parser.add_argument("--dotenv", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--tree-id", action="append", dest="tree_ids", help="Repeat to run a subset from the manifest; default is all five")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--exemplar", type=Path, default=DEFAULT_EXEMPLAR, help="Canonical one-shot exemplar JSON; created from bp_diagnosis if missing")
    parser.add_argument("--max-workers", type=int, default=2, help="Concurrent Gemini calls; lower values reduce rate-limit failures")
    parser.add_argument("--pass-criteria", type=Path, default=DEFAULT_PASS_CRITERIA)
    parser.add_argument("--max-rounds", type=int, default=10, help="Maximum verifier/repair rounds, capped at 10; stops earlier when every tree passes")
    args = parser.parse_args()

    if args.max_rounds < 1 or args.max_rounds > 10:
        raise SystemExit("--max-rounds must be between 1 and 10")

    load_dotenv(args.dotenv)
    api_key = os.environ.get("GEMINI_KEY")
    if not api_key:
        raise SystemExit("GEMINI_KEY is missing")
    model = os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash"
    bundle, image_map = build_extraction_context(args.manifest)
    manifest_tree_ids = [tree["id"] for tree in bundle["trees"]]
    tree_ids = args.tree_ids or manifest_tree_ids
    unknown_tree_ids = sorted(set(tree_ids) - set(manifest_tree_ids))
    if unknown_tree_ids:
        raise SystemExit("unknown tree id(s): " + ", ".join(unknown_tree_ids))
    pass_criteria = json.loads(args.pass_criteria.read_text(encoding="utf-8"))
    if pass_criteria.get("criteriaVersion") != "decision-tree-pass-criteria.v1" or pass_criteria.get("maxRounds") != 10:
        raise SystemExit("invalid strict pass criteria file")
    if args.exemplar.exists():
        exemplar = json.loads(args.exemplar.read_text(encoding="utf-8"))
        exemplar_errors = validate_exemplar(exemplar)
    else:
        raise SystemExit(f"one-shot exemplar does not exist: {args.exemplar}")
    exemplar_errors = validate_exemplar(exemplar)
    if exemplar_errors:
        raise SystemExit("invalid one-shot exemplar: " + "; ".join(exemplar_errors))
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.out_dir or ROOT / "runs" / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    client = GeminiClient(api_key, model)

    source_text = {
        tree_id: f"[REFERENCE IMAGE ATTACHED] {image_map[tree_id].name}\nUse the attached image as the primary evidence for this tree."
        for tree_id in tree_ids
    }
    source_images = {tree_id: [image_map[tree_id]] for tree_id in tree_ids}
    selected_trees = {tree["id"]: tree for tree in bundle["trees"] if tree["id"] in tree_ids}
    write_json(run_dir / "input.json", {"treeIds": tree_ids, "manifest": str(args.manifest), "sourceImages": {tree_id: [str(path) for path in paths] for tree_id, paths in source_images.items()}, "model": model, "oneShotExemplar": str(args.exemplar), "oneShotExemplarVersion": exemplar.get("exemplarVersion"), "passCriteria": str(args.pass_criteria), "passCriteriaVersion": pass_criteria.get("criteriaVersion"), "maxRounds": args.max_rounds})
    write_json(run_dir / "source_text.json", source_text)

    evidence = run_parallel(
        tree_ids,
        lambda tree_id: client.generate_json("evidence:" + tree_id, evidence_prompt(selected_trees[tree_id], source_text[tree_id], bundle), evidence_schema(), image_paths=source_images[tree_id]),
        args.max_workers,
    )
    write_json(run_dir / "evidence_initial_agents.json", evidence)
    evidence_repair_history: list[dict[str, Any]] = []
    for evidence_round in range(1, args.max_rounds + 1):
        evidence_errors_for_round = {
            tree_id: evidence_report_errors(evidence.get(tree_id)) + evidence_completeness_errors(evidence.get(tree_id), tree_id, pass_criteria)
            for tree_id in tree_ids
        }
        repair_ids = [tree_id for tree_id in tree_ids if evidence_errors_for_round[tree_id]]
        if not repair_ids:
            break
        repaired = run_parallel(
            repair_ids,
            lambda tree_id: generate_or_error(
                client,
                f"evidence-repair:r{evidence_round}:" + tree_id,
                evidence_repair_prompt(selected_trees[tree_id], evidence.get(tree_id, {}), evidence_errors_for_round[tree_id], source_text[tree_id], bundle),
                evidence_schema(),
                image_paths=source_images[tree_id],
            ),
            args.max_workers,
        )
        record = {
            "round": evidence_round,
            "repairTreeIds": repair_ids,
            "errorsBeforeRepair": evidence_errors_for_round,
            "repairs": repaired,
        }
        evidence_repair_history.append(record)
        write_json(run_dir / f"evidence_repair_round_{evidence_round:02d}.json", record)
        evidence.update({tree_id: report for tree_id, report in repaired.items()})
    write_json(run_dir / "evidence_repair_history.json", {"maxRounds": args.max_rounds, "rounds": evidence_repair_history})
    write_json(run_dir / "evidence_agents.json", evidence)
    evidence_errors = {
        tree_id: evidence_report_errors(evidence.get(tree_id)) + evidence_completeness_errors(evidence.get(tree_id), tree_id, pass_criteria)
        for tree_id in tree_ids
    }
    for tree_id in tree_ids:
        report = evidence.get(tree_id)
        if isinstance(report, dict) and report.get("missingEvidence"):
            evidence_errors[tree_id].append(f"evidence missingEvidence is not empty: {report.get('missingEvidence')}")

    # Stage 1: extract variables, then run a dedicated variable verifier/repair
    # conversation. The tree builder is gated until every requested tree's
    # variable catalog has passed this stage.
    variable_attempts: dict[str, list[dict[str, Any]]] = {}
    variable_agent_reports: dict[str, dict[str, Any]] = {}
    variable_verifications: dict[str, dict[str, Any]] = {}
    variable_round_history: list[dict[str, Any]] = []
    variable_passed_tree_ids: set[str] = set()
    variable_tree_errors: dict[str, list[str]] = {}
    normalized_evidence: dict[str, dict[str, Any]] = {}
    working_bundle = bundle

    for tree_id in tree_ids:
        tree_attempts: list[dict[str, Any]] = []
        tree_errors: list[str] = []
        previous_proposal: dict[str, Any] = {}
        tree_variable_ids: set[str] = set()
        final_verification: dict[str, Any] = {}
        for variable_round in range(1, args.max_rounds + 1):
            evidence_pack = {tree_id: evidence.get(tree_id, {})}
            if variable_round == 1:
                proposal_prompt = variable_prompt(evidence_pack, working_bundle, tree_id)
                proposal_role = f"variable-architect:{tree_id}"
            else:
                proposal_prompt = variable_repair_prompt(
                    tree_id,
                    previous_proposal,
                    final_verification,
                    normalized_evidence.get(tree_id, evidence.get(tree_id, {})),
                    working_bundle,
                    tree_errors,
                )
                proposal_role = f"variable-repair:r{variable_round}:{tree_id}"
            raw_proposal = generate_or_error(client, proposal_role, proposal_prompt, variable_schema())
            proposal, id_canonicalization_changes = canonicalize_variable_proposal(raw_proposal)
            proposed_values = decode_json_value(proposal.get("variablesJson"), None) if isinstance(proposal, dict) else None
            if not isinstance(proposed_values, list) or not proposed_values:
                proposal_errors = ["variablesJson must contain at least one variable object"]
                candidate_bundle = working_bundle
            else:
                candidate_bundle, proposal_errors = merge_variable_proposal(
                    working_bundle,
                    proposal,
                    replace_ids=tree_variable_ids,
                )

            # A locally invalid proposal is never committed to the shared
            # catalog. A locally valid proposal is committed provisionally so
            # the verifier can inspect the exact catalog the builder would see.
            if proposal_errors:
                candidate_bundle = working_bundle
            else:
                working_bundle = candidate_bundle
                tree_variable_ids.update(
                    item.get("id")
                    for item in proposed_values
                    if isinstance(item, dict) and isinstance(item.get("id"), str)
                )

            # Evidence extraction uses image-facing shorthand IDs and several
            # predicate notations. Normalize it against the exact catalog that
            # this verifier/build step will receive. Raw evidence remains in
            # evidence_agents.json for auditability.
            evidence_for_verifier = canonicalize_evidence_claims(
                evidence.get(tree_id, {}),
                tree_id,
                candidate_bundle,
            )
            normalized_evidence[tree_id] = evidence_for_verifier
            evidence_variable_errors = evidence_variable_reference_errors(evidence_for_verifier, candidate_bundle)

            raw_verification = generate_or_error(
                client,
                f"variable-verifier:r{variable_round}:{tree_id}",
                variable_verifier_prompt(tree_id, proposal, evidence_for_verifier, candidate_bundle, proposal_errors),
                variable_verifier_schema(),
            )
            verification, verification_normalization_changes = normalize_variable_verification(raw_verification)
            verifier_errors = strict_variable_verifier_errors(verification) + evidence_variable_errors
            tree_errors = proposal_errors + verifier_errors
            final_verification = verification
            previous_proposal = proposal
            record = {
                "stage": "variables",
                "treeId": tree_id,
                "round": variable_round,
                "rawProposal": raw_proposal,
                "proposal": proposal,
                "idCanonicalizationChanges": id_canonicalization_changes,
                "rawVerification": raw_verification,
                "localErrors": proposal_errors,
                "verification": verification,
                "verificationNormalizationChanges": verification_normalization_changes,
                "evidenceVariableErrors": evidence_variable_errors,
                "strictErrors": verifier_errors,
                "passed": not tree_errors,
            }
            tree_attempts.append(record)
            variable_round_history.append(record)
            write_json(run_dir / f"variable_round_{tree_id}_{variable_round:02d}.json", record)
            if not tree_errors:
                variable_passed_tree_ids.add(tree_id)
                break

        variable_attempts[tree_id] = tree_attempts
        variable_verifications[tree_id] = final_verification
        variable_agent_reports[tree_id] = previous_proposal or {"status": "pipeline_error", "code": "no_variable_attempt"}
        variable_tree_errors[tree_id] = tree_errors

    variable_errors = [
        f"{tree_id}: {error}"
        for tree_id, errors in variable_tree_errors.items()
        for error in errors
    ]
    variable_proposal = {
        "variablesJson": working_bundle.get("variables", []),
        "derivationRulesJson": "[]",
        "warnings": [],
    }
    write_json(run_dir / "variable_agent.json", variable_proposal)
    write_json(run_dir / "variable_agent_attempts.json", variable_attempts)
    write_json(run_dir / "variable_verifier_agents.json", variable_verifications)
    write_json(run_dir / "evidence_canonical.json", normalized_evidence)
    write_json(run_dir / "variable_conversation_history.json", {
        "stage": "variables",
        "maxRounds": args.max_rounds,
        "passedTreeIds": sorted(variable_passed_tree_ids),
        "failedTreeIds": sorted(set(tree_ids) - variable_passed_tree_ids),
        "rounds": variable_round_history,
    })

    # Stage gate: no tree is built from a partial or unverified variable
    # catalog. This makes the dependency explicit and fail-closed.
    all_variables_passed = variable_passed_tree_ids == set(tree_ids) and not variable_errors
    if all_variables_passed:
        drafts_raw = run_parallel(
            tree_ids,
            lambda tree_id: generate_or_error(client, "builder:" + tree_id, tree_builder_prompt(selected_trees[tree_id], normalized_evidence.get(tree_id, evidence.get(tree_id, {})), variable_proposal, working_bundle, exemplar), reduced_response_schema(), image_paths=source_images[tree_id]),
            args.max_workers,
        )
        drafts = {tree_id: normalise_or_error(draft, tree_id) for tree_id, draft in drafts_raw.items()}
    else:
        drafts = {
            tree_id: {
                "id": tree_id,
                "status": "validation_error",
                "code": "variable_gate_blocked",
                "errors": variable_tree_errors.get(tree_id, ["variable stage did not pass"]),
            }
            for tree_id in tree_ids
        }
    write_json(run_dir / "tree_builder_agents.json", drafts)

    # Agent conversation loop: verifier feedback is sent to a repair agent,
    # whose output is verified again. The loop stops on all-pass or a hard cap.
    verifications: dict[str, Any] = {}
    round_history: list[dict[str, Any]] = []
    repair_attempted_tree_ids: list[str] = []
    loop_status = "max_rounds_exhausted"
    if not all_variables_passed:
        loop_status = "blocked_variable_gate"
    for round_index in range(1, args.max_rounds + 1):
        if not all_variables_passed:
            break
        local_errors = {
            tree_id: candidate_validation_errors(tree_id, drafts.get(tree_id, {}), working_bundle) + evidence_errors.get(tree_id, [])
            for tree_id in tree_ids
        }
        verifications = run_parallel(
            tree_ids,
            lambda tree_id: generate_or_error(
                client,
                f"verifier:r{round_index}:" + tree_id,
                verifier_prompt(drafts.get(tree_id, {}), normalized_evidence.get(tree_id, evidence.get(tree_id, {})), working_bundle, pass_criteria),
                verifier_schema(),
                image_paths=source_images[tree_id],
            ),
            args.max_workers,
        )
        failed_ids = [
            tree_id for tree_id in tree_ids
            if local_errors.get(tree_id)
            or strict_verifier_errors(verifications.get(tree_id, {}), pass_criteria)
        ]
        round_record = {
            "round": round_index,
            "draftTreeIds": list(tree_ids),
            "localStructuralErrors": local_errors,
            "verifications": verifications,
            "strictPassErrors": {tree_id: strict_verifier_errors(verifications.get(tree_id, {}), pass_criteria) for tree_id in tree_ids},
            "failedTreeIds": failed_ids,
        }
        round_history.append(round_record)
        write_json(run_dir / f"round_{round_index:02d}.json", round_record)
        write_json(run_dir / "verifier_agents.json", verifications)

        if not failed_ids:
            loop_status = "passed"
            break
        if round_index == args.max_rounds:
            break

        repair_ids = [
            tree_id for tree_id in failed_ids
            if verifications.get(tree_id, {}).get("status") not in {"agent_error", "validation_error", "pipeline_error"}
        ]
        repair_attempted_tree_ids.extend(repair_ids)
        feedback = {
            tree_id: {
                **(verifications.get(tree_id, {}) if isinstance(verifications.get(tree_id), dict) else {}),
                "localStructuralErrors": local_errors.get(tree_id, []),
                "strictPassErrors": strict_verifier_errors(verifications.get(tree_id, {}), pass_criteria),
            }
            for tree_id in repair_ids
        }
        repaired_raw = run_parallel(
            repair_ids,
            lambda tree_id: generate_or_error(
                client,
                f"repair:r{round_index}:" + tree_id,
                repair_prompt(drafts[tree_id], feedback[tree_id], normalized_evidence.get(tree_id, evidence.get(tree_id, {})), working_bundle, exemplar, pass_criteria),
                reduced_response_schema(),
                image_paths=source_images[tree_id],
            ),
            args.max_workers,
        ) if repair_ids else {}
        repaired = {tree_id: normalise_or_error(draft, tree_id) for tree_id, draft in repaired_raw.items()}
        write_json(run_dir / f"repair_round_{round_index:02d}.json", {"round": round_index, "treeIds": repair_ids, "feedback": feedback, "repairs": repaired})
        drafts.update({tree_id: draft for tree_id, draft in repaired.items() if draft.get("status") not in {"agent_error", "validation_error", "pipeline_error"}})

        if not repair_ids and failed_ids:
            loop_status = "blocked_agent_failure"
            break

    write_json(run_dir / "conversation_history.json", {
        "loopStatus": loop_status,
        "maxRounds": args.max_rounds,
        "roundsCompleted": len(round_history),
        "rounds": round_history,
        "repairAttemptedTreeIds": repair_attempted_tree_ids,
    })

    agent_failure = any(has_agent_failure(payload) for payload in (evidence, variable_agent_reports, variable_verifications, variable_proposal, drafts, verifications))
    if agent_failure:
        manager = {
            "status": "blocked",
            "approvedTreeIdsJson": "[]",
            "requiredFixesJson": json.dumps({"reason": "one_or_more_agents_failed", "agentErrors": {"evidence": evidence, "variable": variable_proposal, "drafts": drafts, "verifications": verifications}}, ensure_ascii=False),
            "variableChangesJson": "[]",
            "finalNotesJson": "Local fail-closed manager fallback: an agent/API failure was detected; no tree is eligible for automatic promotion.",
            "mode": "local_fail_closed_fallback",
        }
    else:
        manager = generate_or_error(client, "manager", manager_prompt(working_bundle, normalized_evidence, variable_proposal, variable_verifications, drafts, verifications, pass_criteria), manager_schema())
    write_json(run_dir / "manager.json", manager)

    approved_ids = set(parse_json_string(manager.get("approvedTreeIdsJson"), []))
    structural_errors: dict[str, list[str]] = {}
    if variable_errors:
        structural_errors["variable_proposal"] = variable_errors
    for tree_id in tree_ids:
        draft = drafts.get(tree_id, {})
        structural_errors[tree_id] = candidate_validation_errors(tree_id, draft, working_bundle) + evidence_errors.get(tree_id, [])
        verification = verifications.get(tree_id, {})
        structural_errors[tree_id].extend(strict_verifier_errors(verification, pass_criteria))

    final_bundle = None
    summary = None
    if manager.get("status") == "ready_for_review" and not any(structural_errors.values()) and approved_ids == set(tree_ids):
        final_bundle = json.loads(json.dumps(working_bundle))
        final_bundle["bundleVersion"] = "0.1.1"
        final_bundle["clinicalStatus"] = "under_review"
        final_bundle["clinicalReviewRequired"] = True
        final_bundle["trees"] = [drafts.get(tree["id"], tree) if tree["id"] in approved_ids else tree for tree in final_bundle["trees"]]
        try:
            summary = validate_bundle_payload(final_bundle)
            write_json(run_dir / "bundle.draft.json", final_bundle)
        except Exception as exc:
            structural_errors["bundle"] = [str(exc)]
            final_bundle = None

    report = {
        "runDir": str(run_dir),
        "model": model,
        "treeIds": tree_ids,
        "oneShotExemplar": str(args.exemplar),
        "oneShotExemplarVersion": exemplar.get("exemplarVersion"),
        "passCriteria": str(args.pass_criteria),
        "passCriteriaVersion": pass_criteria.get("criteriaVersion"),
        "repairAttemptedTreeIds": repair_attempted_tree_ids,
        "variableStage": {
            "passedTreeIds": sorted(variable_passed_tree_ids),
            "failedTreeIds": sorted(set(tree_ids) - variable_passed_tree_ids),
            "allPassed": all_variables_passed,
            "errors": variable_tree_errors,
        },
        "loopStatus": loop_status,
        "maxRounds": args.max_rounds,
        "roundsCompleted": len(round_history),
        "managerMode": manager.get("mode", "llm"),
        "managerStatus": manager.get("status"),
        "approvedTreeIds": sorted(approved_ids),
        "structuralErrors": structural_errors,
        "bundleDraftWritten": final_bundle is not None,
        "bundleSummary": summary,
        "nextStep": "clinical review before approval" if final_bundle is not None else "fix manager/verifier issues and rerun",
    }
    write_json(run_dir / "run_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def validate_bundle_payload(bundle: dict[str, Any]) -> dict[str, int]:
    temp_path = ROOT / ".tmp_generated_bundle.json"
    try:
        write_json(temp_path, bundle)
        return validate_bundle(temp_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


if __name__ == "__main__":
    main()
