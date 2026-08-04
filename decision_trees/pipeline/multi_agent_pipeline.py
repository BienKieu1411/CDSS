#!/usr/bin/env python3
"""Multi-agent Gemini pipeline for automatic guideline -> decision-tree drafts.

Pipeline:
  evidence agents (parallel)
      -> variable architect
      -> tree builders (parallel)
      -> verifier agents (parallel)
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
    return f"""Role: Evidence Extractor Agent.
Extract only guideline evidence needed for tree '{tree['id']}'. Do not design the tree yet.
For every claim, output a machine-readable predicateJson using the variable names visible in the image where possible, plus sourceRefsJson with exact sourceId and page/section/tableOrFigure. If the source is a matrix or table, emit one claim for every clinically distinct row/column cell and preserve all category combinations; do not summarize the whole matrix as one claim.
Capture thresholds, inclusivity, exceptions, and missing-data requirements. Only put an item in missingEvidence when the supplied image omits information that is necessary to implement a pictured branch. Do not mark ancillary guideline thresholds as missing when the image provides a categorical input such as a risk-factor count or a named comorbidity.
Existing source catalog: {json.dumps(bundle['sourceDocuments'], ensure_ascii=False)}
Existing variable catalog: {json.dumps([v['id'] for v in bundle['variables']], ensure_ascii=False)}
Tree purpose: {tree['purpose']}
Guideline text:
{source_text}
Return JSON only."""


def variable_prompt(evidence: dict[str, Any], bundle: dict[str, Any], tree_id: str | None = None) -> str:
    scope = f"for tree '{tree_id}'" if tree_id else "for the requested trees"
    return f"""Role: Variable Architect Agent.
Build a draft variable catalog {scope} from the evidence pack. This is a bootstrap run: the existing catalog may be empty. Create every variable needed by the target tree, including variables written by inference/end nodes. Do not omit a variable merely because it appears in another tree; shared variables may be repeated and will be deduplicated by the aggregator.
Return variablesJson as a JSON array of variable objects, not as a JSON-encoded string. Every variable must include id, label, dataType, unit, definition, sourceSystem, requiredForEvaluation, sourceRefs, and derivedFrom. Use only these dataType values: boolean, integer, number, string, enum. Use only these sourceSystem values: patient, encounter, vitals, laboratory, medication, problem_list, derived, clinician_input. Variable IDs must match ^[a-z][a-zA-Z0-9]*(\\.[a-zA-Z0-9_]+)*$; use dot-separated IDs such as bp.systolicMmHg, never spaces or free-form names. For enum variables include allowedValues. Every sourceRef must be an object with the exact sourceId and tableOrFigure filename from the source catalog. Distinguish raw input variables from derived variables. Include derivation rules as a JSON string.
Every variable used with gt/gte/lt/lte must have dataType number or integer. Blood pressure values must be represented as separate numeric systolic and diastolic variables; never represent a BP reading used in a threshold predicate as one string/composite variable. A unit of mmHg is not sufficient to make a composite string computable.
Existing catalog: {json.dumps(bundle['variables'], ensure_ascii=False)}
Evidence pack: {json.dumps(evidence, ensure_ascii=False)}
Source catalog: {json.dumps(bundle['sourceDocuments'], ensure_ascii=False)}
Return JSON only. Do not write executable code or free-text clinical rules."""


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


def manager_prompt(bundle: dict[str, Any], evidence: dict[str, Any], variable_proposal: dict[str, Any], drafts: dict[str, Any], verifications: dict[str, Any], pass_criteria: dict[str, Any]) -> str:
    return f"""Role: Manager/Aggregator Agent.
Coordinate the multi-agent result. Decide whether the generated set is ready for human clinical review. You may approve a tree only when its verifier status is pass and its source coverage is adequate.
Do not approve missing or speculative evidence. Return approvedTreeIdsJson, requiredFixesJson, variableChangesJson, and finalNotesJson as valid JSON strings.
Status should be 'ready_for_review' only when all requested trees are structurally complete and no P0/P1 issue exists; otherwise 'blocked'.
Baseline bundle metadata: {json.dumps({'bundleId': bundle['bundleId'], 'bundleVersion': bundle['bundleVersion']}, ensure_ascii=False)}
Evidence pack: {json.dumps(evidence, ensure_ascii=False)}
Variable proposal: {json.dumps(variable_proposal, ensure_ascii=False)}
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
    ref["page"] = page
    ref.setdefault("section", document.get("title", "Evidence"))
    # The sourceId -> image filename mapping is authoritative. This repairs a
    # harmless provider formatting error without changing provenance.
    ref["tableOrFigure"] = filename
    ref.setdefault("note", "Evidence reference supplied by the extraction agent.")
    return ref, None


def merge_variable_proposal(bundle: dict[str, Any], proposal: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
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
        if variable["id"] in existing:
            continue
        if invalid_ref:
            continue
        existing[variable["id"]] = variable
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
    write_json(run_dir / "evidence_agents.json", evidence)
    evidence_errors = {
        tree_id: (
            ["evidence report is missing or invalid"]
            if not isinstance(evidence.get(tree_id), dict)
            else [f"evidence missingEvidence is not empty: {evidence[tree_id].get('missingEvidence')}"]
            if evidence[tree_id].get("missingEvidence")
            else []
        )
        for tree_id in tree_ids
    }

    variable_attempts: dict[str, list[dict[str, Any]]] = {}
    variable_agent_reports: dict[str, dict[str, Any]] = {}
    working_bundle = bundle
    variable_errors: list[str] = []
    for tree_id in tree_ids:
        tree_attempts: list[dict[str, Any]] = []
        tree_errors: list[str] = []
        for variable_attempt in range(1, 4):
            retry_feedback = ""
            if tree_errors:
                retry_feedback = (
                    "\nThe previous proposal was rejected by the local canonical normalizer. "
                    "Correct every listed issue before returning the complete catalog for this tree; preserve every previously valid variable and do not return only a partial correction.\n"
                    f"REJECTED ISSUES: {json.dumps(tree_errors, ensure_ascii=False)}\n"
                )
            proposal = generate_or_error(
                client,
                f"variable-architect:{tree_id}" if variable_attempt == 1 else f"variable-architect:{tree_id}:retry:{variable_attempt}",
                variable_prompt({tree_id: evidence.get(tree_id, {})}, working_bundle, tree_id) + retry_feedback,
                variable_schema(),
            )
            proposed_values = decode_json_value(proposal.get("variablesJson"), None) if isinstance(proposal, dict) else None
            if not isinstance(proposed_values, list) or not proposed_values:
                proposal_errors = ["variablesJson must contain at least one variable object"]
                candidate_bundle = working_bundle
            else:
                candidate_bundle, proposal_errors = merge_variable_proposal(working_bundle, proposal)
            working_bundle = candidate_bundle
            tree_errors = proposal_errors
            tree_attempts.append({"attempt": variable_attempt, "proposal": proposal, "errors": proposal_errors})
            if not proposal_errors:
                break
        variable_attempts[tree_id] = tree_attempts
        variable_agent_reports[tree_id] = tree_attempts[-1]["proposal"] if tree_attempts else {"status": "pipeline_error", "code": "no_variable_attempt"}
        variable_errors.extend(f"{tree_id}: {error}" for error in tree_errors)

    variable_proposal = {
        "variablesJson": working_bundle.get("variables", []),
        "derivationRulesJson": "[]",
        "warnings": [],
    }
    write_json(run_dir / "variable_agent.json", variable_proposal)
    write_json(run_dir / "variable_agent_attempts.json", variable_attempts)

    drafts_raw = run_parallel(
        tree_ids,
        lambda tree_id: generate_or_error(client, "builder:" + tree_id, tree_builder_prompt(selected_trees[tree_id], evidence.get(tree_id, {}), variable_proposal, working_bundle, exemplar), reduced_response_schema(), image_paths=source_images[tree_id]),
        args.max_workers,
    )
    drafts = {tree_id: normalise_or_error(draft, tree_id) for tree_id, draft in drafts_raw.items()}
    write_json(run_dir / "tree_builder_agents.json", drafts)

    # Agent conversation loop: verifier feedback is sent to a repair agent,
    # whose output is verified again. The loop stops on all-pass or a hard cap.
    verifications: dict[str, Any] = {}
    round_history: list[dict[str, Any]] = []
    repair_attempted_tree_ids: list[str] = []
    loop_status = "max_rounds_exhausted"
    for round_index in range(1, args.max_rounds + 1):
        local_errors = {
            tree_id: candidate_validation_errors(tree_id, drafts.get(tree_id, {}), working_bundle) + evidence_errors.get(tree_id, [])
            for tree_id in tree_ids
        }
        verifications = run_parallel(
            tree_ids,
            lambda tree_id: generate_or_error(
                client,
                f"verifier:r{round_index}:" + tree_id,
                verifier_prompt(drafts.get(tree_id, {}), evidence.get(tree_id, {}), working_bundle, pass_criteria),
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
                repair_prompt(drafts[tree_id], feedback[tree_id], evidence.get(tree_id, {}), working_bundle, exemplar, pass_criteria),
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

    agent_failure = any(has_agent_failure(payload) for payload in (evidence, variable_agent_reports, variable_proposal, drafts, verifications))
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
        manager = generate_or_error(client, "manager", manager_prompt(working_bundle, evidence, variable_proposal, drafts, verifications, pass_criteria), manager_schema())
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
