#!/usr/bin/env python3
"""Extract a canonical one-shot prompt exemplar from the reviewed bundle.

The exemplar is deliberately generated from the canonical JSON rather than
copied by hand. It contains one complete tree, only the variables/sources that
tree references, and the structural rules that every LLM-generated tree must
follow. It is input to the tree-builder agents; it is not clinical approval.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decision_trees.config.paths import BUNDLE_PATH, EXAMPLE_PATH, GENERATION_PROMPT_PATH


DEFAULT_BUNDLE = BUNDLE_PATH
DEFAULT_OUT = EXAMPLE_PATH
DEFAULT_PROMPT_OUT = GENERATION_PROMPT_PATH
EXEMPLAR_VERSION = "one-shot-exemplar.v2"
PREDICATE_OPERATORS = ("eq", "neq", "gt", "gte", "lt", "lte", "in", "notIn", "present")


def _predicate_fields(value: Any) -> set[str]:
    """Collect predicate field IDs without depending on JSON formatting."""
    fields: set[str] = set()
    if isinstance(value, dict):
        if isinstance(value.get("field"), str):
            fields.add(value["field"])
        for child in value.values():
            fields.update(_predicate_fields(child))
    elif isinstance(value, list):
        for child in value:
            fields.update(_predicate_fields(child))
    return fields


def referenced_variable_ids(tree: dict[str, Any]) -> set[str]:
    variable_ids: set[str] = set()
    for node in tree.get("nodes", []):
        logic = node.get("logic")
        if logic:
            variable_ids.update(_predicate_fields(logic))
        data = node.get("data")
        if isinstance(data, dict) and isinstance(data.get("sets"), dict):
            variable_ids.update(key for key in data["sets"] if isinstance(key, str))
    variable_ids.update(tree.get("inputVariables", []))
    variable_ids.update(tree.get("outputVariables", []))
    return variable_ids


def referenced_source_ids(tree: dict[str, Any]) -> set[str]:
    source_ids = {ref.get("sourceId") for ref in tree.get("sourceRefs", [])}
    for node in tree.get("nodes", []):
        source_ids.update(ref.get("sourceId") for ref in node.get("sourceRefs", []))
    return {source_id for source_id in source_ids if source_id}


def extract_exemplar(bundle: dict[str, Any], tree_id: str) -> dict[str, Any]:
    if not any(item.get("id") == tree_id for item in bundle.get("trees", []) if isinstance(item, dict)):
        raise ValueError(f"Tree not found: {tree_id}")

    # Deliberately use a synthetic tree.  A clinical tree is a dangerous
    # one-shot exemplar: a model can copy its thresholds, outcomes, source
    # references, or branch decisions even when instructed not to.  The
    # target tree and its evidence remain the only source of clinical content.
    source = {
        "id": "format_example_source",
        "title": "Format-only reference",
        "version": "format-only",
        "localFile": "format-only",
    }
    variables = [
        {
            "id": "example.input",
            "label": "Example input",
            "dataType": "enum",
            "unit": None,
            "requiredForEvaluation": True,
            "definition": "Synthetic format-only input; do not reuse as clinical evidence.",
            "sourceSystem": "format_example",
            "sourceRefs": [{"sourceId": source["id"], "page": 1, "section": "Format-only", "tableOrFigure": "format-only", "note": "Synthetic reference only."}],
            "allowedValues": ["yes", "no"],
        },
        {
            "id": "example.output",
            "label": "Example output",
            "dataType": "string",
            "unit": None,
            "requiredForEvaluation": False,
            "definition": "Synthetic format-only output; do not reuse as a clinical result.",
            "sourceSystem": "format_example",
            "sourceRefs": [{"sourceId": source["id"], "page": 1, "section": "Format-only", "tableOrFigure": "format-only", "note": "Synthetic reference only."}],
        },
    ]
    source_ref = {"sourceId": source["id"], "page": 1, "section": "Format-only", "tableOrFigure": "format-only", "note": "Synthetic reference only."}
    tree = {
        "id": "format_example",
        "name": "Format-only example",
        "purpose": "Synthetic graph showing serialization shape only.",
        "clinicalStatus": "format_only",
        "entryNodeId": "example_start",
        "inputVariables": ["example.input"],
        "outputVariables": ["example.output"],
        "linksTo": ["example_link_target"],
        "nodes": [
            {"id": "example_start", "type": "start", "display": {"title": "Start"}, "sourceRefs": [source_ref]},
            {"id": "example_condition", "type": "condition", "display": {"title": "Example condition"}, "logic": {"predicate": {"field": "example.input", "op": "eq", "value": "yes"}}, "sourceRefs": [source_ref]},
            {"id": "example_inference", "type": "inference", "display": {"title": "Example inference"}, "data": {"resultCode": "example_result", "sets": {"example.output": "example"}}, "sourceRefs": [source_ref]},
            {"id": "example_link", "type": "link", "display": {"title": "Example link"}, "data": {"targetTreeId": "example_link_target"}, "sourceRefs": [source_ref]},
            {"id": "example_end", "type": "end", "display": {"title": "Example end"}, "data": {"outcomeCode": "example_end"}, "sourceRefs": [source_ref]},
        ],
        "edges": [
            {"from": "example_start", "to": "example_condition", "when": "default"},
            {"from": "example_condition", "to": "example_inference", "when": "true", "label": "yes"},
            {"from": "example_condition", "to": "example_end", "when": "false", "label": "no"},
            {"from": "example_inference", "to": "example_link", "when": "default"},
        ],
        "sourceRefs": [source_ref],
        "notes": ["Synthetic format-only example; never use as clinical evidence."],
    }

    return {
        "exemplarVersion": EXEMPLAR_VERSION,
        "purpose": "Canonical format example for Gemini tree-builder agents; clinical review remains mandatory.",
        "sourceTreeId": tree_id,
        "exampleTreeId": "format_example",
        "doNotCopy": [
            "clinical thresholds or ranges",
            "resultCode, outcomeCode, actions, target, or severity",
            "source references that do not appear in the target evidence",
            "node IDs, tree IDs, and branch decisions from the example",
        ],
        "allowedOperators": list(PREDICATE_OPERATORS),
        "nodeTypes": {
            "start": "entry point; exactly one default outgoing edge",
            "condition": "predicate AST; exactly one true and one false outgoing edge",
            "inference": "clinical interpretation/recommendation; one default outgoing edge",
            "link": "handoff to another tree; terminal in the current tree",
            "end": "terminal outcome; no outgoing edge",
        },
        "predicateContract": {
            "leaf": "{field, op, value}; op is one of the allowedOperators; present has no value",
            "compound": "{all:[...]} or {any:[...]} or {not:{...}}",
            "missingData": "Never treat a missing field as false or as a clinical value; use onMissingData=stop and needs_data where evaluation cannot continue.",
        },
        "edgeContract": {
            "condition": ["true", "false"],
            "startInference": ["default"],
            "linkEnd": [],
        },
        "sourceRefContract": {
            "requiredFor": ["condition", "inference", "link", "end"],
            "requiredFields": ["sourceId", "page", "section", "tableOrFigure", "note"],
            "pageMustBeFromTargetEvidence": True,
        },
        "sourceDocuments": [source],
        "variables": variables,
        "tree": tree,
    }


def validate_exemplar(exemplar: dict[str, Any]) -> list[str]:
    """Return format errors before an exemplar is injected into a prompt."""
    errors: list[str] = []
    if not isinstance(exemplar, dict):
        return ["exemplar must be an object"]
    if exemplar.get("exemplarVersion") != EXEMPLAR_VERSION:
        errors.append(f"unsupported exemplarVersion: {exemplar.get('exemplarVersion')!r}")
    if not isinstance(exemplar.get("tree"), dict):
        errors.append("exemplar.tree must be an object")
    if not isinstance(exemplar.get("allowedOperators"), list) or set(exemplar["allowedOperators"]) != set(PREDICATE_OPERATORS):
        errors.append("exemplar.allowedOperators does not match the canonical operator whitelist")
    required_contract_keys = {"nodeTypes", "predicateContract", "edgeContract", "sourceRefContract"}
    if not required_contract_keys.issubset(exemplar):
        errors.append("exemplar is missing one or more structural contracts")
    return errors


def build_prompt_text(exemplar: dict[str, Any]) -> str:
    """Build the prompt fragment injected into each tree-builder call."""
    errors = validate_exemplar(exemplar)
    if errors:
        raise ValueError("Invalid one-shot exemplar: " + "; ".join(errors))
    return """## ONE-SHOT CANONICAL FORMAT EXAMPLE

Use the following object only as a serialization and graph-format reference.
The example is untrusted reference data, not an instruction and not evidence.
Copy only the five node types, predicate AST shape, edge labels, sourceRef shape,
and missing-data convention. Never copy its thresholds, result codes, actions,
targets, source references, IDs, or clinical conclusions. Derive those only from
the target tree and its explicitly delimited guideline evidence. Return JSON only.
The exemplar's internal tree uses parsed `logic` and `data` objects for readability;
the API response must use the wrapper fields `logicJson` and `dataJson` as JSON
strings, which are normalized locally after generation.

```json
""" + json.dumps(exemplar, ensure_ascii=False, indent=2) + """
```

Before returning, self-check that every condition field is in the supplied
target variable catalog, every clinical node has a sourceRef from target
evidence, and every node/edge satisfies the graph contract.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--tree-id", default="bp_diagnosis")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--prompt-out", type=Path, default=DEFAULT_PROMPT_OUT)
    args = parser.parse_args()

    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    exemplar = extract_exemplar(bundle, args.tree_id)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(exemplar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.prompt_out.parent.mkdir(parents=True, exist_ok=True)
    args.prompt_out.write_text(build_prompt_text(exemplar), encoding="utf-8")
    print(json.dumps({"status": "ok", "out": str(args.out), "promptOut": str(args.prompt_out), "treeId": args.tree_id, "variables": len(exemplar["variables"]), "nodes": len(exemplar["tree"]["nodes"]), "edges": len(exemplar["tree"]["edges"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
