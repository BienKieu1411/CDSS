#!/usr/bin/env python3
"""Fail-closed structural validator for the CDSS decision-tree bundle."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decision_trees.config.paths import BUNDLE_PATH


OPS = {"eq", "neq", "gt", "gte", "lt", "lte", "in", "notIn", "present", "contains", "lengthEq", "lengthGte", "lengthIn"}
NODE_TYPES = {"start", "condition", "branch", "inference", "link", "end"}
EDGE_WHEN = {"true", "false", "default"}
DATA_TYPES = {"boolean", "integer", "number", "string", "enum", "array"}


def fail(message: str) -> None:
    raise ValueError(message)


def validate_predicate_value(variable: dict[str, Any], op: str, value: Any, where: str) -> None:
    if op in {"in", "notIn", "lengthIn"}:
        if not isinstance(value, list) or not value:
            fail(f"{where}: operator {op} requires a non-empty list value")
        values = value
    else:
        values = [value]

    data_type = variable.get("dataType")
    if op == "contains" and data_type != "array":
        fail(f"{where}: operator contains requires an array variable")
    if op in {"lengthEq", "lengthGte", "lengthIn"} and data_type != "array":
        fail(f"{where}: operator {op} requires an array variable")
    if op in {"lengthEq", "lengthGte"} and (isinstance(value, bool) or not isinstance(value, int)):
        fail(f"{where}: operator {op} requires an integer length value")
    if op == "lengthIn" and any(isinstance(item, bool) or not isinstance(item, int) for item in values):
        fail(f"{where}: operator lengthIn requires integer length values")
    allowed_values = variable.get("allowedValues", [])
    for item in values:
        if data_type == "boolean" and not isinstance(item, bool):
            fail(f"{where}: expected boolean value for {variable['id']}")
        if data_type == "integer" and (isinstance(item, bool) or not isinstance(item, int)):
            fail(f"{where}: expected integer value for {variable['id']}")
        if data_type == "number" and (isinstance(item, bool) or not isinstance(item, (int, float))):
            fail(f"{where}: expected numeric value for {variable['id']}")
        if data_type == "string" and not isinstance(item, str):
            fail(f"{where}: expected string value for {variable['id']}")
        if data_type == "enum" and item not in allowed_values:
            fail(f"{where}: value {item!r} is not allowed for {variable['id']}")
    if op in {"gt", "gte", "lt", "lte", "lengthEq", "lengthGte", "lengthIn"} and data_type not in {"integer", "number", "array"}:
        fail(f"{where}: operator {op} requires a numeric variable")


def walk_predicate(predicate: Any, variable_map: dict[str, dict[str, Any]], where: str) -> set[str]:
    """Validate a predicate and return every variable referenced by it."""
    if not isinstance(predicate, dict):
        fail(f"{where}: predicate must be an object")
    if "field" in predicate:
        field = predicate["field"]
        if not isinstance(field, str) or not field:
            fail(f"{where}: field must be a non-empty string")
        if field not in variable_map:
            fail(f"{where}: unknown variable {field}")
        extra_keys = set(predicate) - {"field", "op", "value", "valueField"}
        if extra_keys:
            fail(f"{where}: leaf predicate has unknown keys {sorted(extra_keys)}")
        op = predicate.get("op")
        if op not in OPS:
            fail(f"{where}: unsupported operator {op}")
        has_value = "value" in predicate
        has_value_field = "valueField" in predicate
        if op != "present" and has_value == has_value_field:
            fail(f"{where}: operator {op} requires exactly one of value or valueField")
        if op == "present" and (has_value or has_value_field):
            fail(f"{where}: present operator must not include value or valueField")
        if has_value:
            validate_predicate_value(variable_map[field], op, predicate["value"], where)
        if has_value_field:
            value_field = predicate["valueField"]
            if not isinstance(value_field, str) or not value_field:
                fail(f"{where}: valueField must be a non-empty string")
            if value_field not in variable_map:
                fail(f"{where}: unknown valueField {value_field}")
            if op not in {"eq", "neq", "gt", "gte", "lt", "lte"}:
                fail(f"{where}: valueField is only supported with scalar comparison operators")
            if variable_map[field].get("dataType") not in {"integer", "number"}:
                fail(f"{where}: operator {op} requires a numeric variable")
            if variable_map[value_field].get("dataType") not in {"integer", "number"}:
                fail(f"{where}: valueField {value_field} must be numeric")
            return {field, value_field}
        return {field}

    keys = [key for key in ("all", "any", "not") if key in predicate]
    if len(keys) != 1 or set(predicate) != set(keys):
        fail(f"{where}: predicate must contain exactly one of field/all/any/not")
    key = keys[0]
    if key == "not":
        return walk_predicate(predicate[key], variable_map, f"{where}.not")

    children = predicate[key]
    if not isinstance(children, list) or not children:
        fail(f"{where}.{key}: must be a non-empty list")
    used_fields: set[str] = set()
    for index, child in enumerate(children):
        used_fields.update(walk_predicate(child, variable_map, f"{where}.{key}[{index}]"))
    return used_fields


def validate_source_refs(refs: Any, source_ids: set[str], where: str) -> None:
    if refs is None:
        return
    if not isinstance(refs, list):
        fail(f"{where}: sourceRefs must be a list")
    for index, ref in enumerate(refs):
        ref_where = f"{where}.sourceRefs[{index}]"
        if not isinstance(ref, dict) or not isinstance(ref.get("sourceId"), str) or not ref["sourceId"]:
            fail(f"{ref_where}: source reference requires a non-empty sourceId")
        if ref["sourceId"] not in source_ids:
            fail(f"{ref_where}: unknown source {ref['sourceId']}")
        page = ref.get("page")
        if page is not None and (not isinstance(page, int) or isinstance(page, bool) or page < 1):
            fail(f"{ref_where}: invalid source page")


def validate_bundle(path: Path) -> dict[str, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        fail("bundle root must be an object")
    if data.get("formatVersion") != "decision-tree-bundle.v1":
        fail("formatVersion must be decision-tree-bundle.v1")
    for key in ("bundleId", "bundleVersion", "locale"):
        if not isinstance(data.get(key), str) or not data[key]:
            fail(f"{key} must be a non-empty string")

    source_documents = data.get("sourceDocuments")
    if not isinstance(source_documents, list) or not source_documents:
        fail("sourceDocuments must be a non-empty list")
    source_ids: set[str] = set()
    for index, source in enumerate(source_documents):
        if not isinstance(source, dict) or not isinstance(source.get("id"), str) or not source["id"]:
            fail(f"sourceDocuments[{index}]: requires a non-empty id")
        if source["id"] in source_ids:
            fail(f"duplicate source id {source['id']}")
        source_ids.add(source["id"])

    variables = data.get("variables")
    if not isinstance(variables, list) or not variables:
        fail("variables must be a non-empty list")
    variable_map: dict[str, dict[str, Any]] = {}
    for index, variable in enumerate(variables):
        if not isinstance(variable, dict) or not isinstance(variable.get("id"), str) or not variable["id"]:
            fail(f"variables[{index}]: requires a non-empty id")
        variable_id = variable["id"]
        if variable_id in variable_map:
            fail(f"duplicate variable id {variable_id}")
        if variable.get("dataType") not in DATA_TYPES:
            fail(f"{variable_id}: invalid dataType")
        variable_map[variable_id] = variable
    variable_ids = set(variable_map)
    for variable in variables:
        validate_source_refs(variable.get("sourceRefs", []), source_ids, f"variable {variable['id']}")
        for derived_from in variable.get("derivedFrom", []):
            if derived_from not in variable_ids:
                fail(f"variable {variable['id']}: unknown derivedFrom variable {derived_from}")

    trees = data.get("trees")
    if not isinstance(trees, list) or not trees:
        fail("trees must be a non-empty list")
    tree_ids: set[str] = set()
    for index, tree in enumerate(trees):
        if not isinstance(tree, dict) or not isinstance(tree.get("id"), str) or not tree["id"]:
            fail(f"trees[{index}]: requires a non-empty id")
        tree_id = tree["id"]
        if tree_id in tree_ids:
            fail(f"duplicate tree id {tree_id}")
        tree_ids.add(tree_id)
    global_links: dict[str, set[str]] = {tree_id: set() for tree_id in tree_ids}

    node_count = 0
    edge_count = 0
    link_count = 0
    for tree in trees:
        tree_id = tree["id"]
        if tree.get("clinicalStatus") not in {None, "draft", "under_review", "approved", "retired"}:
            fail(f"{tree_id}: invalid clinicalStatus")

        input_variables = tree.get("inputVariables", [])
        output_variables = tree.get("outputVariables", [])
        links_to = tree.get("linksTo", [])
        if not isinstance(input_variables, list) or not isinstance(output_variables, list) or not isinstance(links_to, list):
            fail(f"{tree_id}: inputVariables, outputVariables and linksTo must be lists")
        if any(not isinstance(item, str) for item in input_variables + output_variables + links_to):
            fail(f"{tree_id}: declared IDs must be strings")
        if len(input_variables) != len(set(input_variables)):
            fail(f"{tree_id}: duplicate input variable")
        if len(output_variables) != len(set(output_variables)):
            fail(f"{tree_id}: duplicate output variable")
        if len(links_to) != len(set(links_to)):
            fail(f"{tree_id}: duplicate linksTo target")
        for variable_id in input_variables + output_variables:
            if variable_id not in variable_ids:
                fail(f"{tree_id}: unknown declared variable {variable_id}")
        validate_source_refs(tree.get("sourceRefs", []), source_ids, tree_id)
        used_fields: set[str] = set()
        if "entryPreconditions" in tree:
            used_fields.update(walk_predicate(tree["entryPreconditions"], variable_map, f"{tree_id}.entryPreconditions"))

        raw_nodes = tree.get("nodes")
        raw_edges = tree.get("edges")
        if not isinstance(raw_nodes, list) or not raw_nodes:
            fail(f"{tree_id}: nodes must be a non-empty list")
        if not isinstance(raw_edges, list):
            fail(f"{tree_id}: edges must be a list")

        nodes: dict[str, dict[str, Any]] = {}
        for index, node in enumerate(raw_nodes):
            if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"]:
                fail(f"{tree_id}/nodes[{index}]: requires a non-empty id")
            node_id = node["id"]
            if node_id in nodes:
                fail(f"{tree_id}: duplicate node id {node_id}")
            nodes[node_id] = node
        entry_node_id = tree.get("entryNodeId")
        if not isinstance(entry_node_id, str) or entry_node_id not in nodes:
            fail(f"{tree_id}: entryNodeId does not exist")
        node_count += len(nodes)

        start_nodes = [node_id for node_id, node in nodes.items() if node.get("type") == "start"]
        if start_nodes != [entry_node_id]:
            fail(f"{tree_id}: exactly the entryNodeId must be the single start node")

        produced_variables: set[str] = set()
        for node in nodes.values():
            node_id = node["id"]
            node_type = node.get("type")
            if node_type not in NODE_TYPES:
                fail(f"{tree_id}/{node_id}: invalid node type")
            if not isinstance(node.get("sourceRefs"), list) or not node["sourceRefs"]:
                fail(f"{tree_id}/{node_id}: every node requires at least one sourceRef")
            if node.get("onMissingData") not in {None, "stop"}:
                fail(f"{tree_id}/{node_id}: onMissingData must be stop/omitted; fail-closed runtime does not allow skip")
            validate_source_refs(node.get("sourceRefs", []), source_ids, f"{tree_id}/{node_id}")

            if node_type == "condition":
                logic = node.get("logic")
                predicate = logic.get("predicate") if isinstance(logic, dict) else None
                if predicate is None:
                    fail(f"{tree_id}/{node_id}: condition is missing logic.predicate")
                used_fields.update(walk_predicate(predicate, variable_map, f"{tree_id}/{node_id}"))

            if node_type == "branch":
                logic = node.get("logic")
                cases = logic.get("cases") if isinstance(logic, dict) else None
                if not isinstance(cases, list) or not cases:
                    fail(f"{tree_id}/{node_id}: branch requires a non-empty logic.cases list")
                case_ids: set[str] = set()
                for case_index, case in enumerate(cases):
                    case_where = f"{tree_id}/{node_id}.logic.cases[{case_index}]"
                    if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"]:
                        fail(f"{case_where}: case requires a non-empty id")
                    if case["id"] in case_ids:
                        fail(f"{case_where}: duplicate case id {case['id']}")
                    case_ids.add(case["id"])
                    if not isinstance(case.get("label"), str) or not case["label"]:
                        fail(f"{case_where}: case requires a label")
                    used_fields.update(walk_predicate(case.get("predicate"), variable_map, f"{case_where}.predicate"))

            if node_type in {"link", "inference", "end"}:
                node_data = node.get("data")
                if not isinstance(node_data, dict):
                    fail(f"{tree_id}/{node_id}: data must be an object")
                if node_type == "link":
                    target = node_data.get("targetTreeId")
                    if target not in tree_ids and node_data.get("callMode") != "navigate_only":
                        fail(f"{tree_id}/{node_id}: unknown link target {target}")
                    if target in tree_ids:
                        global_links[tree_id].add(target)
                    link_count += 1
                elif node_type == "inference":
                    if not isinstance(node_data.get("resultCode"), str) or not node_data["resultCode"]:
                        fail(f"{tree_id}/{node_id}: inference is missing data.resultCode")
                elif not isinstance(node_data.get("outcomeCode"), str) or not node_data["outcomeCode"]:
                    fail(f"{tree_id}/{node_id}: end is missing data.outcomeCode")
                sets = node_data.get("sets", {})
                if not isinstance(sets, dict):
                    fail(f"{tree_id}/{node_id}: data.sets must be an object")
                unknown_sets = set(sets) - variable_ids
                if unknown_sets:
                    fail(f"{tree_id}/{node_id}: data.sets contains unknown variables {sorted(unknown_sets)}")
                produced_variables.update(sets)

        undeclared_fields = used_fields - set(input_variables)
        if undeclared_fields:
            fail(f"{tree_id}: predicates reference undeclared input variables {sorted(undeclared_fields)}")
        undeclared_outputs = produced_variables - set(output_variables)
        if undeclared_outputs:
            fail(f"{tree_id}: data.sets variables missing from outputVariables {sorted(undeclared_outputs)}")

        adjacency: dict[str, list[str]] = {node_id: [] for node_id in nodes}
        incoming: dict[str, int] = {node_id: 0 for node_id in nodes}
        edge_keys: set[tuple[str, str, str]] = set()
        for index, edge in enumerate(raw_edges):
            if not isinstance(edge, dict):
                fail(f"{tree_id}/edges[{index}]: edge must be an object")
            edge_from = edge.get("from")
            edge_to = edge.get("to")
            edge_when = edge.get("when")
            if not isinstance(edge_from, str) or not isinstance(edge_to, str):
                fail(f"{tree_id}/edges[{index}]: from/to must be strings")
            if edge_from not in nodes or edge_to not in nodes:
                fail(f"{tree_id}: edge references unknown node")
            if edge_from == edge_to:
                fail(f"{tree_id}: self-loop at {edge_from}")
            if not isinstance(edge_when, str) or not edge_when:
                fail(f"{tree_id}: invalid edge.when {edge_when}")
            edge_key = (edge_from, edge_to, edge_when)
            if edge_key in edge_keys:
                fail(f"{tree_id}: duplicate edge {edge_key}")
            edge_keys.add(edge_key)
            adjacency[edge_from].append(edge_to)
            incoming[edge_to] += 1
            edge_count += 1

        for node_id, node in nodes.items():
            outgoing = [edge for edge in raw_edges if edge["from"] == node_id]
            when_counts = Counter(edge["when"] for edge in outgoing)
            if node["type"] == "condition":
                if when_counts != Counter({"true": 1, "false": 1}):
                    fail(f"{tree_id}/{node_id}: condition must have one true and one false edge")
            elif node["type"] == "branch":
                expected = Counter(case["id"] for case in node["logic"]["cases"])
                if "default" in when_counts:
                    expected["default"] = 1
                if when_counts != expected:
                    fail(f"{tree_id}/{node_id}: branch edges must match case IDs, with an optional default edge")
            elif node["type"] in {"start", "inference"}:
                if when_counts != Counter({"default": 1}):
                    fail(f"{tree_id}/{node_id}: {node['type']} must have one default edge")
            elif node["type"] == "link" and outgoing:
                fail(f"{tree_id}/{node_id}: link must be terminal")
            elif node["type"] == "end" and outgoing:
                # A conclusion may hand off to a separate link node. The end
                # remains the visible clinical outcome; the link is the
                # navigation edge to the next tree.
                if len(outgoing) != 1 or outgoing[0]["when"] != "default":
                    fail(f"{tree_id}/{node_id}: end may only have one default handoff edge")

        if incoming[entry_node_id] != 0:
            fail(f"{tree_id}: entryNodeId must have no incoming edges")
        for node_id, count in incoming.items():
            if node_id != entry_node_id and count == 0:
                fail(f"{tree_id}: non-entry node {node_id} has no incoming edge")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                fail(f"{tree_id}: cycle detected at {node_id}")
            if node_id in visited:
                return
            visiting.add(node_id)
            for child in adjacency[node_id]:
                visit(child)
            visiting.remove(node_id)
            visited.add(node_id)

        visit(entry_node_id)
        unreachable = set(nodes) - visited
        if unreachable:
            fail(f"{tree_id}: unreachable nodes {sorted(unreachable)}")

        declared_links = {target for target in links_to if target in tree_ids}
        if declared_links != global_links[tree_id]:
            fail(f"{tree_id}: linksTo does not match LINK nodes: declared={sorted(declared_links)}, actual={sorted(global_links[tree_id])}")

    global_visiting: set[str] = set()
    global_visited: set[str] = set()

    def visit_tree(tree_id: str) -> None:
        if tree_id in global_visiting:
            fail(f"global tree-link cycle detected at {tree_id}")
        if tree_id in global_visited:
            return
        global_visiting.add(tree_id)
        for target_tree_id in global_links[tree_id]:
            visit_tree(target_tree_id)
        global_visiting.remove(tree_id)
        global_visited.add(tree_id)

    for tree_id in tree_ids:
        visit_tree(tree_id)

    return {"trees": len(tree_ids), "variables": len(variable_ids), "nodes": node_count, "edges": edge_count, "links": link_count}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", nargs="?", default=BUNDLE_PATH)
    args = parser.parse_args()
    summary = validate_bundle(Path(args.bundle))
    print(json.dumps({"status": "ok", **summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
