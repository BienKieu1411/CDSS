#!/usr/bin/env python3
"""Deterministic evaluator for the decision-tree bundle.

The evaluator intentionally contains no clinical interpretation beyond the
whitelisted predicate operators. Clinical meaning belongs in the JSON bundle.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decision_trees.config.paths import BUNDLE_PATH
from decision_trees.runtime.validate_decision_tree_bundle import validate_bundle


class MissingData(Exception):
    """Raised when a predicate cannot be decided from the supplied context."""

    def __init__(self, fields: str | Iterable[str]):
        if isinstance(fields, str):
            ordered_fields = [fields]
        else:
            ordered_fields = list(fields)
        self.fields = tuple(dict.fromkeys(ordered_fields))
        if not self.fields:
            raise ValueError("MissingData requires at least one field")
        self.field = self.fields[0]
        super().__init__(", ".join(self.fields))


def merge_missing(*errors: MissingData) -> MissingData:
    fields: list[str] = []
    for error in errors:
        fields.extend(error.fields)
    return MissingData(fields)


@dataclass
class EvalState:
    context: dict[str, Any]
    trace: list[dict[str, Any]]
    links_visited: list[str]
    source_refs: list[dict[str, Any]]
    decision_sets: dict[str, Any]


def get_value(context: dict[str, Any], field: str) -> Any:
    if field not in context or context[field] is None:
        raise MissingData(field)
    return context[field]


def evaluate_predicate(predicate: dict[str, Any], context: dict[str, Any]) -> bool:
    if "field" in predicate:
        field = predicate["field"]
        op = predicate["op"]
        if op == "present":
            return field in context and context[field] is not None
        actual = get_value(context, field)
        if "valueField" in predicate:
            expected = get_value(context, predicate["valueField"])
        else:
            expected = predicate.get("value")
        if op == "eq":
            return actual == expected
        if op == "neq":
            return actual != expected
        if op == "gt":
            return actual > expected
        if op == "gte":
            return actual >= expected
        if op == "lt":
            return actual < expected
        if op == "lte":
            return actual <= expected
        if op == "in":
            return actual in expected
        if op == "notIn":
            return actual not in expected
        raise ValueError(f"unsupported operator: {op}")
    if "all" in predicate:
        missing: list[MissingData] = []
        for child in predicate["all"]:
            try:
                if not evaluate_predicate(child, context):
                    return False
            except MissingData as exc:
                missing.append(exc)
        if missing:
            raise merge_missing(*missing)
        return True
    if "any" in predicate:
        missing: list[MissingData] = []
        for child in predicate["any"]:
            try:
                if evaluate_predicate(child, context):
                    return True
            except MissingData as exc:
                missing.append(exc)
        if missing:
            raise merge_missing(*missing)
        return False
    if "not" in predicate:
        return not evaluate_predicate(predicate["not"], context)
    raise ValueError(f"invalid predicate: {predicate}")


def add_sources(state: EvalState, node: dict[str, Any]) -> None:
    for source_ref in node.get("sourceRefs", []):
        if source_ref not in state.source_refs:
            state.source_refs.append(source_ref)


def select_edge(edges: list[dict[str, Any]], from_id: str, when: str) -> dict[str, Any]:
    matches = [edge for edge in edges if edge["from"] == from_id and edge["when"] == when]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {when} edge from {from_id}, got {len(matches)}")
    return matches[0]


def append_trace(state: EvalState, event: dict[str, Any]) -> None:
    state.trace.append(event)


def execute_tree(bundle: dict[str, Any], tree_id: str, state: EvalState, active_trees: tuple[str, ...] = ()) -> dict[str, Any]:
    if tree_id in active_trees:
        raise ValueError(f"tree link cycle: {' -> '.join(active_trees + (tree_id,))}")
    tree_map = {tree["id"]: tree for tree in bundle["trees"]}
    if tree_id not in tree_map:
        raise ValueError(f"unknown tree: {tree_id}")
    tree = tree_map[tree_id]
    for source_ref in tree.get("sourceRefs", []):
        if source_ref not in state.source_refs:
            state.source_refs.append(source_ref)
    if "entryPreconditions" in tree:
        try:
            precondition_value = evaluate_predicate(tree["entryPreconditions"], state.context)
        except MissingData as missing:
            append_trace(state, {"treeId": tree_id, "type": "entry_precondition", "status": "missing", "missingData": list(missing.fields)})
            return {"treeId": tree_id, "status": "needs_data", "missingData": list(missing.fields)}
        append_trace(state, {
            "treeId": tree_id,
            "type": "entry_precondition",
            "status": "passed" if precondition_value else "not_met",
            "value": precondition_value,
        })
        if not precondition_value:
            return {"treeId": tree_id, "status": "invalid_input", "reason": "entry_precondition_not_met"}
    nodes = {node["id"]: node for node in tree["nodes"]}
    edges = tree["edges"]
    current_id = tree["entryNodeId"]
    result: dict[str, Any] = {"treeId": tree_id}

    while True:
        node = nodes[current_id]
        add_sources(state, node)
        node_type = node["type"]
        if node_type == "start":
            append_trace(state, {"treeId": tree_id, "nodeId": current_id, "type": node_type, "status": "entered"})
            edge = select_edge(edges, current_id, "default")
            current_id = edge["to"]
            continue

        if node_type == "condition":
            try:
                value = evaluate_predicate(node["logic"]["predicate"], state.context)
            except MissingData as missing:
                policy = node.get("onMissingData", "stop")
                append_trace(state, {
                    "treeId": tree_id,
                    "nodeId": current_id,
                    "type": node_type,
                    "status": "missing",
                    "field": missing.field,
                    "missingData": list(missing.fields),
                    "policy": policy,
                    "effectivePolicy": "needs_data",
                })
                # Missing data must never be converted to a clinical false
                # value.  This also makes legacy/unknown policies fail safe.
                return {"treeId": tree_id, "status": "needs_data", "missingData": list(missing.fields)}
            append_trace(state, {"treeId": tree_id, "nodeId": current_id, "type": node_type, "value": value})
            edge = select_edge(edges, current_id, "true" if value else "false")
            current_id = edge["to"]
            continue

        if node_type == "inference":
            data = node.get("data", {})
            sets = data.get("sets", {})
            state.context.update(sets)
            state.decision_sets.update(sets)
            append_trace(state, {
                "treeId": tree_id,
                "nodeId": current_id,
                "type": node_type,
                "resultCode": data.get("resultCode"),
                "sets": sets,
                "severity": data.get("severity"),
                "actions": data.get("actions", []),
            })
            result.update({"status": "inference", "resultCode": data.get("resultCode"), "sets": sets, "severity": data.get("severity"), "actions": data.get("actions", [])})
            edge = select_edge(edges, current_id, "default")
            current_id = edge["to"]
            continue

        if node_type == "link":
            target = node["data"]["targetTreeId"]
            state.links_visited.append(target)
            append_trace(state, {"treeId": tree_id, "nodeId": current_id, "type": node_type, "targetTreeId": target})
            child_result = execute_tree(bundle, target, state, active_trees + (tree_id,))
            result.update(child_result)
            return result

        if node_type == "end":
            data = node.get("data", {})
            sets = data.get("sets", {}) if isinstance(data, dict) else {}
            if isinstance(sets, dict):
                state.context.update(sets)
                state.decision_sets.update(sets)
            append_trace(state, {
                "treeId": tree_id,
                "nodeId": current_id,
                "type": node_type,
                "outcomeCode": data.get("outcomeCode"),
                "actions": data.get("actions", []),
                "sets": sets,
            })
            result.update({"status": "completed", "outcomeCode": data.get("outcomeCode"), "actions": data.get("actions", []), "sets": sets})
            if isinstance(data.get("resultCode"), str):
                result["resultCode"] = data["resultCode"]
            if isinstance(data.get("severity"), str):
                result["severity"] = data["severity"]
            return result

        raise ValueError(f"unsupported node type: {node_type}")


def run(bundle_path: Path, tree_id: str, context: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(context, dict):
        raise TypeError("context must be a JSON object")
    validation_summary = validate_bundle(bundle_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    state = EvalState(context=dict(context), trace=[], links_visited=[], source_refs=[], decision_sets={})
    result = execute_tree(bundle, tree_id, state)
    result.update({
        "entryTreeId": tree_id,
        "terminalTreeId": result.get("treeId"),
        "bundleId": bundle.get("bundleId"),
        "bundleVersion": bundle.get("bundleVersion"),
        "context": state.context,
        "linksVisited": state.links_visited,
        "trace": state.trace,
        "sourceRefs": state.source_refs,
        "validation": validation_summary,
    })
    result["sets"] = dict(state.decision_sets)
    result["decision"] = {
        "status": result.get("status"),
        "resultCode": result.get("resultCode"),
        "outcomeCode": result.get("outcomeCode"),
        "sets": dict(state.decision_sets),
        "severity": result.get("severity"),
        "actions": result.get("actions", []),
        "missingData": result.get("missingData", []),
        "reason": result.get("reason"),
    }
    return result


CLINICAL_FLOW_ORDER = (
    "bp_thresholds_targets",
    "optimized_hypertension_treatment",
)


def _unique_items(items: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result


def run_clinical_flow(
    bundle_path: Path,
    context: dict[str, Any],
    *,
    start_tree_id: str = "bp_thresholds_targets",
) -> dict[str, Any]:
    """Run the ordered clinical flow and pass each tree's context forward.

    Tree 2 therefore writes the treatment targets before Tree 3 evaluates the
    encounter BP. Tree 3 may continue into Tree 5 through its LINK node.
    """
    if start_tree_id in CLINICAL_FLOW_ORDER:
        tree_ids = list(CLINICAL_FLOW_ORDER[CLINICAL_FLOW_ORDER.index(start_tree_id):])
    elif start_tree_id == "uncontrolled_resistant_hypertension":
        tree_ids = [start_tree_id]
    else:
        raise ValueError(f"tree {start_tree_id!r} is not a clinical-flow entrypoint")

    current_context = dict(context)
    steps: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    links_visited: list[str] = []
    source_refs: list[dict[str, Any]] = []
    sets: dict[str, Any] = {}
    final_result: dict[str, Any] | None = None

    for tree_id in tree_ids:
        step = run(bundle_path, tree_id, current_context)
        final_result = step
        current_context.update(step.get("context", {}))
        sets.update(step.get("sets", {}))
        trace.extend(step.get("trace", []))
        links_visited = _unique_items([*links_visited, *step.get("linksVisited", [])])
        source_refs = _unique_items([*source_refs, *step.get("sourceRefs", [])])
        steps.append({
            "treeId": tree_id,
            "status": step.get("status"),
            "resultCode": step.get("resultCode"),
            "outcomeCode": step.get("outcomeCode"),
            "terminalTreeId": step.get("terminalTreeId"),
            "missingData": step.get("missingData", []),
        })
        if step.get("status") != "completed":
            break

    assert final_result is not None
    result = {
        "status": final_result.get("status"),
        "resultCode": final_result.get("resultCode"),
        "outcomeCode": final_result.get("outcomeCode"),
        "actions": final_result.get("actions", []),
        "sets": sets,
        "entryTreeId": start_tree_id,
        "terminalTreeId": final_result.get("terminalTreeId"),
        "bundleId": final_result.get("bundleId"),
        "bundleVersion": final_result.get("bundleVersion"),
        "context": current_context,
        "linksVisited": links_visited,
        "trace": trace,
        "sourceRefs": source_refs,
        "validation": final_result.get("validation"),
        "steps": steps,
        "decision": {
            "status": final_result.get("status"),
            "resultCode": final_result.get("resultCode"),
            "outcomeCode": final_result.get("outcomeCode"),
            "sets": sets,
            "severity": final_result.get("severity"),
            "actions": final_result.get("actions", []),
            "missingData": final_result.get("missingData", []),
            "reason": final_result.get("reason"),
        },
    }
    if final_result.get("missingData"):
        result["missingData"] = final_result["missingData"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, default=BUNDLE_PATH)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--tree-id")
    mode.add_argument("--flow-start-tree-id")
    parser.add_argument("--input", type=Path, required=True, help="JSON object containing flattened variable IDs")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    context = payload.get("variables", payload)
    result = run_clinical_flow(args.bundle, context, start_tree_id=args.flow_start_tree_id) if args.flow_start_tree_id else run(args.bundle, args.tree_id, context)
    for key in ("patientId", "encounterId", "contextSnapshotId", "asOf"):
        if key in payload:
            result[key] = payload[key]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
