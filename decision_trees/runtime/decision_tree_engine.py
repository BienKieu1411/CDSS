#!/usr/bin/env python3
"""Deterministic evaluator for the decision-tree bundle.

The evaluator intentionally contains no clinical interpretation beyond the
whitelisted predicate operators. Clinical meaning belongs in the JSON bundle.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decision_trees.config.paths import BUNDLE_PATH, CONTRACTS_DIR
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


def normalize_diagnosis_codes(raw_codes: Any) -> set[str]:
    """Normalize the patient's comma/newline-separated ICD-10/SNOMED codes."""
    if raw_codes is None:
        return set()
    values = raw_codes if isinstance(raw_codes, list) else re.split(r"[,;\n\r\t ]+", str(raw_codes))
    return {re.sub(r"[^A-Z0-9]", "", str(value).upper()) for value in values if str(value).strip()}


def _has_value(context: dict[str, Any], field: str) -> bool:
    return field in context and context[field] is not None and context[field] != ""


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def _reference_date(context: dict[str, Any]) -> date:
    return _parse_date(context.get("asOf")) or date.today()


def _derive_any_known(context: dict[str, Any], fields: Iterable[str]) -> bool | None:
    field_list = list(fields)
    known = [field for field in field_list if _has_value(context, field)]
    if any(context[field] is True for field in known):
        return True
    if len(known) == len(field_list):
        return False
    return None


def derive_patient_problem_variables(context: dict[str, Any]) -> dict[str, Any]:
    """Derive disease flags from the patient's coded problem list.

    The UI accepts one patient-level code list. The clinical tree consumes
    stable boolean variables, so the mapping is kept deterministic here and
    cannot be overridden by a manually supplied boolean.
    """
    if "patient.diagnosisCodes" not in context or context["patient.diagnosisCodes"] is None:
        return {}
    codes = normalize_diagnosis_codes(context.get("patient.diagnosisCodes"))

    def has_exact(*values: str) -> bool:
        return any(value in codes for value in values)

    def has_prefix(*prefixes: str) -> bool:
        return any(any(code.startswith(prefix) for prefix in prefixes) for code in codes)

    derived = {
        "comorbidity.earlyMenopause": has_exact("373717006", "E283"),
        "comorbidity.diabetes": has_prefix("E08", "E09", "E10", "E11", "E13", "E14"),
        "comorbidity.type2Diabetes": has_prefix("E119"),
        "comorbidity.leftVentricularHypertrophy": has_exact("25488008"),
        "comorbidity.atheroscleroticCvd": has_prefix("I251"),
        "comorbidity.coronaryArteryDisease": has_prefix("I251"),
        "comorbidity.heartFailure": has_prefix("I50"),
        "comorbidity.heartFailureReducedEjectionFraction": has_prefix("I502"),
        "comorbidity.stroke": has_prefix("I63"),
        "comorbidity.peripheralArteryDisease": has_prefix("I739"),
        "comorbidity.atrialFibrillation": has_prefix("I48"),
        "comorbidity.ckd": has_prefix("N18"),
        "risk.ckdStageAtLeast3": any(
            code.startswith(("N183", "N184", "N185", "N186", "N187", "N188", "N189"))
            for code in codes
        ),
    }
    derived["risk.diabetes"] = derived["comorbidity.diabetes"]
    derived["risk.cardiovascularDisease"] = any(derived[key] for key in (
        "comorbidity.atheroscleroticCvd",
        "comorbidity.coronaryArteryDisease",
        "comorbidity.heartFailure",
        "comorbidity.stroke",
        "comorbidity.peripheralArteryDisease",
        "comorbidity.atrialFibrillation",
    ))
    derived["risk.targetOrganDamage"] = any(derived[key] for key in (
        "comorbidity.leftVentricularHypertrophy",
        "risk.ckdStageAtLeast3",
    ))
    derived["comorbidity.targetOrganDamageOrCvd"] = any((
        derived["risk.targetOrganDamage"],
        derived["risk.cardiovascularDisease"],
    ))
    derived["risk.highRiskComorbidity"] = any((
        derived["risk.targetOrganDamage"],
        derived["risk.ckdStageAtLeast3"],
        derived["risk.diabetes"],
        derived["risk.cardiovascularDisease"],
    ))
    derived["treatment.mandatoryIndication"] = any(derived[key] for key in (
        "comorbidity.atheroscleroticCvd",
        "comorbidity.heartFailure",
        "comorbidity.stroke",
        "comorbidity.ckd",
        "comorbidity.diabetes",
    ))
    derived["treatment.hasHighRiskComorbidity"] = derived["risk.highRiskComorbidity"]
    return derived


def derive_patient_measurement_variables(context: dict[str, Any]) -> dict[str, Any]:
    """Derive age, BMI and risk flags from the expected patient measurements.

    A derived value is emitted only when its source value(s) are present. This
    preserves the contract's fail-closed behavior for incomplete patient data.
    """
    derived: dict[str, Any] = {}

    # Latest clinic BP is derived, never manually entered. Prefer the most
    # recent complete pair: visit 3, then visit 2, then visit 1.
    for encounter in (3, 2, 1):
        systolic = context.get(f"bp.office{encounter}.systolicMmHg")
        diastolic = context.get(f"bp.office{encounter}.diastolicMmHg")
        if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in (systolic, diastolic)):
            derived["bp.latest.systolicMmHg"] = systolic
            derived["bp.latest.diastolicMmHg"] = diastolic
            break

    birth_date = _parse_date(context.get("patient.birthDate"))
    if birth_date is not None:
        reference = _reference_date(context)
        age = reference.year - birth_date.year - (
            (reference.month, reference.day) < (birth_date.month, birth_date.day)
        )
        derived["patient.ageYears"] = age

    height = context.get("patient.heightM")
    weight = context.get("patient.weightKg")
    if isinstance(height, (int, float)) and not isinstance(height, bool) and height > 0:
        if isinstance(weight, (int, float)) and not isinstance(weight, bool) and weight >= 0:
            derived["patient.bmi"] = weight / (height * height)

    age = derived.get("patient.ageYears", context.get("patient.ageYears"))
    if isinstance(age, (int, float)) and not isinstance(age, bool):
        derived["risk.ageOver65"] = age > 65

    sex = context.get("patient.sex")
    if isinstance(sex, str) and sex.strip():
        derived["risk.maleSex"] = sex.strip().lower() in {"male", "m", "nam"}

    heart_rate = context.get("vitals.heartRate")
    if isinstance(heart_rate, (int, float)) and not isinstance(heart_rate, bool):
        derived["risk.heartRateOver80"] = heart_rate > 80

    bmi = derived.get("patient.bmi", context.get("patient.bmi"))
    if isinstance(bmi, (int, float)) and not isinstance(bmi, bool):
        derived["risk.overweight"] = bmi >= 25

    e_gfr = context.get("lab.eGfr")
    if isinstance(e_gfr, (int, float)) and not isinstance(e_gfr, bool):
        derived["risk.ckdStageAtLeast3"] = e_gfr < 60

    if _has_value(context, "comorbidity.diabetes"):
        derived["risk.diabetes"] = context["comorbidity.diabetes"] is True

    cardiovascular_fields = (
        "comorbidity.atheroscleroticCvd",
        "comorbidity.coronaryArteryDisease",
        "comorbidity.heartFailure",
        "comorbidity.stroke",
        "comorbidity.peripheralArteryDisease",
        "comorbidity.atrialFibrillation",
    )
    cardiovascular = _derive_any_known(context, cardiovascular_fields)
    if cardiovascular is not None:
        derived["risk.cardiovascularDisease"] = cardiovascular

    target_damage_fields = ("comorbidity.leftVentricularHypertrophy", "risk.ckdStageAtLeast3")
    target_damage = _derive_any_known(
        {**context, **derived},
        target_damage_fields,
    )
    if target_damage is not None:
        derived["risk.targetOrganDamage"] = target_damage

    combined_damage = _derive_any_known(
        {**context, **derived},
        ("risk.targetOrganDamage", "risk.cardiovascularDisease"),
    )
    if combined_damage is not None:
        derived["comorbidity.targetOrganDamageOrCvd"] = combined_damage

    high_risk = _derive_any_known(
        {**context, **derived},
        ("risk.targetOrganDamage", "risk.ckdStageAtLeast3", "risk.diabetes", "risk.cardiovascularDisease"),
    )
    if high_risk is not None:
        derived["risk.highRiskComorbidity"] = high_risk
        derived["treatment.hasHighRiskComorbidity"] = high_risk

    mandatory_fields = (
        "comorbidity.atheroscleroticCvd",
        "comorbidity.heartFailure",
        "comorbidity.stroke",
        "comorbidity.ckd",
        "comorbidity.diabetes",
    )
    mandatory = _derive_any_known({**context, **derived}, mandatory_fields)
    if mandatory is not None:
        derived["treatment.mandatoryIndication"] = mandatory

    # Bảng phân tầng nguy cơ trong guideline liệt kê đúng các YTNC sau:
    # tuổi >65, giới nam, nhịp tim >80, thừa cân, đái tháo đường,
    # LDL-C/triglyceride tăng, tiền sử gia đình bệnh tim mạch sớm,
    # hút thuốc và yếu tố xã hội/môi trường. Không dùng một biến boolean
    # tổng hợp do người dùng tự nhập để tránh đếm sai hoặc đếm trùng.
    factor_fields = (
        "risk.ageOver65",
        "risk.maleSex",
        "risk.heartRateOver80",
        "risk.overweight",
        "risk.diabetes",
        "risk.lipidAbnormality",
        "risk.familyHistoryPrematureCvd",
        "risk.currentSmoker",
        "risk.socialEnvironmentalRisk",
    )
    factor_context = {**context, **derived}
    if all(_has_value(factor_context, field) for field in factor_fields):
        derived["risk.factorCount"] = sum(factor_context[field] is True for field in factor_fields)

    return derived


def _load_drug_class_by_name() -> dict[str, str]:
    """Build the lookup from the persisted medication catalog.

    The catalog is the single source of truth for recognized antihypertensive
    names. Keeping this lookup derived from the JSON prevents Tree 3 and Tree
    5 from silently drifting away from the list maintained by the project.
    """
    catalog_path = CONTRACTS_DIR / "antihypertensive_medication_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    for medication_class in catalog.get("classes", []):
        class_code = medication_class.get("code")
        if not isinstance(class_code, str) or not class_code:
            continue
        for drug in medication_class.get("drugs", []):
            name = drug.get("name") if isinstance(drug, dict) else drug
            if isinstance(name, str) and name.strip():
                mapping[name.strip().lower()] = class_code
    # Common input alias retained for the catalog's hydrochlorothiazide entry.
    mapping.setdefault("hctz", "diuretic")
    mapping.setdefault("torsemide", "diuretic")
    return mapping


DRUG_CLASS_BY_NAME = _load_drug_class_by_name()


def derive_medication_variables(context: dict[str, Any]) -> dict[str, Any]:
    """Derive medication groups and regimen duration from the patient record.

    ``medication.regimenStableWeeks`` is deliberately never accepted as an
    input. It is calculated from the recorded regimen start/change date and
    the encounter reference date so callers cannot manually bypass the
    four-week stability check in Tree 5.
    """
    def map_classes(raw_names: Any) -> tuple[list[str], list[str]]:
        if raw_names is None or raw_names == "":
            return [], []
        values = raw_names if isinstance(raw_names, list) else re.split(r"[,;\n\r\t]+", str(raw_names))
        class_codes: list[str] = []
        unknown_names: list[str] = []
        for value in values:
            name = re.sub(r"\s+", " ", str(value).strip().lower())
            if not name:
                continue
            class_code = DRUG_CLASS_BY_NAME.get(name)
            if class_code and class_code not in class_codes:
                class_codes.append(class_code)
            elif not class_code and name not in unknown_names:
                unknown_names.append(name)
        return class_codes, unknown_names

    derived: dict[str, Any] = {}
    regimen_start = _parse_date(context.get("medication.regimenStartDate"))
    reference = _reference_date(context)
    if regimen_start is not None and regimen_start <= reference:
        derived["medication.regimenStableWeeks"] = (reference - regimen_start).days // 7
    current_codes, current_unknown = map_classes(context.get("medication.currentDrugNames"))
    if current_codes or current_unknown:
        # Keep one canonical representation.  Count and membership checks are
        # evaluated directly against this list by the decision-tree engine.
        derived["medication.currentDrugClassList"] = current_codes

    previous_codes, previous_unknown = map_classes(context.get("medication.previousEncounterDrugNames"))
    if previous_codes or previous_unknown:
        derived["medication.previousEncounterDrugClassList"] = previous_codes
    return derived


def normalize_medication_list_inputs(context: dict[str, Any]) -> dict[str, Any]:
    """Accept UI-friendly comma-separated medication input as canonical lists.

    The contract remains an array: this adapter only handles the convenient
    text representation used by the local UI and CLI callers.
    """
    normalized = dict(context)
    for field in ("medication.currentDrugNames", "medication.previousEncounterDrugNames"):
        value = normalized.get(field)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                normalized[field] = parsed
            else:
                normalized[field] = [item.strip() for item in re.split(r"[,;\n\r\t]+", value) if item.strip()]
    return normalized


def _map_missing_derived_fields(bundle: dict[str, Any], result: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Report missing source fields instead of hiding them behind a derived ID."""
    missing = result.get("missingData")
    if not isinstance(missing, list):
        return result
    variable_map = {variable["id"]: variable for variable in bundle.get("variables", [])}
    expanded: list[str] = []
    for field in missing:
        variable = variable_map.get(field, {})
        sources = variable.get("derivedFrom", []) if variable.get("sourceSystem") == "derived" else []
        unresolved_sources = [source for source in sources if not _has_value(context, source)]
        expanded.extend(unresolved_sources or [field])
    result["missingData"] = list(dict.fromkeys(expanded))
    return result


def derive_bp_control_variables(context: dict[str, Any]) -> dict[str, Any]:
    """Compare the current encounter BP with the target produced by Tree 2.

    Tree 3 labels the check by treatment stage (2, 3 or 4 drug groups), but
    the clinical measurement is the current encounter BP and the target is
    the patient-specific target from Tree 2. The three stage flags therefore
    intentionally share the same deterministic comparison.
    """
    systolic = context.get("bp.latest.systolicMmHg")
    diastolic = context.get("bp.latest.diastolicMmHg")
    target_systolic = context.get("treatment.targetSystolicMmHg")
    target_diastolic = context.get("treatment.targetDiastolicMmHg")
    values = (systolic, diastolic, target_systolic, target_diastolic)
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
        return {}
    controlled = systolic < target_systolic and diastolic < target_diastolic
    return {
        "bp.controlledAfterTwoDrugs": controlled,
        "bp.controlledAfterThreeDrugs": controlled,
        "bp.controlledAfterFourDrugs": controlled,
    }


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
            return _has_value(context, field)
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
        if op == "contains":
            if not isinstance(actual, list):
                raise TypeError(f"{field} must be a list for contains")
            return expected in actual
        if op == "lengthEq":
            if not isinstance(actual, list):
                raise TypeError(f"{field} must be a list for lengthEq")
            return len(actual) == expected
        if op == "lengthGte":
            if not isinstance(actual, list):
                raise TypeError(f"{field} must be a list for lengthGte")
            return len(actual) >= expected
        if op == "lengthIn":
            if not isinstance(actual, list):
                raise TypeError(f"{field} must be a list for lengthIn")
            return len(actual) in expected
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

        if node_type == "branch":
            selected_case = None
            missing: list[MissingData] = []
            for case in node.get("logic", {}).get("cases", []):
                try:
                    if evaluate_predicate(case["predicate"], state.context):
                        selected_case = case["id"]
                        break
                except MissingData as exc:
                    missing.append(exc)
            if selected_case is None and missing:
                merged = merge_missing(*missing)
                append_trace(state, {
                    "treeId": tree_id,
                    "nodeId": current_id,
                    "type": node_type,
                    "status": "missing",
                    "missingData": list(merged.fields),
                    "effectivePolicy": "needs_data",
                })
                return {"treeId": tree_id, "status": "needs_data", "missingData": list(merged.fields)}
            if selected_case is None:
                default_edges = [edge for edge in edges if edge["from"] == current_id and edge["when"] == "default"]
                if not default_edges:
                    append_trace(state, {
                        "treeId": tree_id,
                        "nodeId": current_id,
                        "type": node_type,
                        "status": "invalid_input",
                        "reason": "no_branch_case_matched",
                    })
                    return {"treeId": tree_id, "status": "invalid_input", "reason": "no_branch_case_matched"}
            selected_when = selected_case or "default"
            append_trace(state, {
                "treeId": tree_id,
                "nodeId": current_id,
                "type": node_type,
                "selectedCase": selected_when,
            })
            edge = select_edge(edges, current_id, selected_when)
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
            result.update({"status": "inference", "resultCode": data.get("resultCode"), "outcomeCode": data.get("outcomeCode"), "sets": sets, "severity": data.get("severity"), "actions": data.get("actions", [])})
            edge = select_edge(edges, current_id, "default")
            current_id = edge["to"]
            continue

        if node_type == "link":
            data = node.get("data", {})
            target = data["targetTreeId"]
            state.links_visited.append(target)
            append_trace(state, {"treeId": tree_id, "nodeId": current_id, "type": node_type, "targetTreeId": target})
            if node["data"].get("callMode") == "navigate_only":
                result.update({
                    "status": "completed",
                    "linkTargetTreeId": target,
                    "outcomeCode": data.get("outcomeCode") or result.get("outcomeCode"),
                })
                return result
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
    initial_context = normalize_medication_list_inputs(context)
    # Do not allow a JSON/API caller to override the derived latest BP.
    initial_context.pop("bp.latest.systolicMmHg", None)
    initial_context.pop("bp.latest.diastolicMmHg", None)
    # This is a derived duration, never a caller-supplied override.
    initial_context.pop("medication.regimenStableWeeks", None)
    initial_context.update(derive_patient_problem_variables(initial_context))
    initial_context.update(derive_patient_measurement_variables(initial_context))
    initial_context.update(derive_medication_variables(initial_context))
    initial_context.update(derive_bp_control_variables(initial_context))
    state = EvalState(context=initial_context, trace=[], links_visited=[], source_refs=[], decision_sets={})
    input_errors = validate_context(bundle, initial_context)
    if input_errors:
        result = {
            "treeId": tree_id,
            "status": "invalid_input",
            "reason": "invalid_context",
            "errors": input_errors,
        }
    else:
        result = execute_tree(bundle, tree_id, state)
    result = _map_missing_derived_fields(bundle, result, initial_context)
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
        "errors": result.get("errors", []),
    }
    return result


CLINICAL_FLOW_ORDER = (
    "bp_diagnosis",
    "hypertension_risk_stratification",
    "bp_thresholds_targets",
    "optimized_hypertension_treatment",
)

CLINICAL_FLOW_ENTRYPOINTS = frozenset((*CLINICAL_FLOW_ORDER, "uncontrolled_resistant_hypertension"))


def validate_context(bundle: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate supplied canonical values before evaluating predicates.

    Unknown keys are deliberately ignored: callers may include transport
    metadata or future variables. Known values are checked against the bundle
    contract so direct Python/CLI calls fail with a structured result instead
    of leaking a comparison/type exception from a predicate.
    """
    variable_map = {variable["id"]: variable for variable in bundle.get("variables", [])}
    errors: list[dict[str, Any]] = []
    for field, value in context.items():
        variable = variable_map.get(field)
        if variable is None or value is None:
            continue
        data_type = variable.get("dataType")
        valid_type = (
            (data_type == "boolean" and isinstance(value, bool))
            or (data_type == "integer" and isinstance(value, int) and not isinstance(value, bool))
            or (data_type == "number" and isinstance(value, (int, float)) and not isinstance(value, bool))
            or (data_type in {"string", "enum"} and isinstance(value, str))
            or (data_type == "array" and isinstance(value, list))
        )
        if not valid_type:
            errors.append({
                "field": field,
                "code": "invalid_type",
                "message": f"{field} must have dataType {data_type}",
            })
            continue
        allowed_values = variable.get("allowedValues")
        if allowed_values and value not in allowed_values:
            errors.append({
                "field": field,
                "code": "not_allowed",
                "message": f"{field} has a value outside allowedValues",
            })
            continue
        rules = variable.get("validation", {})
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if rules.get("minimum") is not None and value < rules["minimum"]:
                errors.append({"field": field, "code": "below_minimum", "message": f"{field} is below its minimum"})
            if rules.get("maximum") is not None and value > rules["maximum"]:
                errors.append({"field": field, "code": "above_maximum", "message": f"{field} is above its maximum"})
        if isinstance(value, str) and rules.get("maxLength") is not None and len(value) > rules["maxLength"]:
            errors.append({"field": field, "code": "too_long", "message": f"{field} exceeds maxLength"})
    return errors


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
    start_tree_id: str = "bp_diagnosis",
) -> dict[str, Any]:
    """Follow the bundle's LINK transitions while carrying context forward.

    A fixed tree order is unsafe: crisis/review branches terminate without a
    link and must not continue into later treatment stages. The bundle is the
    source of truth for the next stage; this function only follows the
    ``linkTargetTreeId`` returned by a navigate-only LINK. A subtree LINK is
    already executed by ``execute_tree`` and therefore ends the flow when its
    child returns.
    """
    if start_tree_id not in CLINICAL_FLOW_ENTRYPOINTS:
        raise ValueError(f"tree {start_tree_id!r} is not a clinical-flow entrypoint")

    current_context = dict(context)
    steps: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    links_visited: list[str] = []
    source_refs: list[dict[str, Any]] = []
    sets: dict[str, Any] = {}
    final_result: dict[str, Any] | None = None

    current_tree_id: str | None = start_tree_id
    visited_tree_ids: set[str] = set()
    while current_tree_id is not None:
        if current_tree_id in visited_tree_ids:
            final_result = {
                "treeId": current_tree_id,
                "status": "invalid_input",
                "reason": "clinical_flow_cycle",
            }
            break
        visited_tree_ids.add(current_tree_id)
        tree_id = current_tree_id
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
            "errors": step.get("errors", []),
        })
        if step.get("status") != "completed":
            break
        current_tree_id = step.get("linkTargetTreeId")

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
            "errors": final_result.get("errors", []),
        },
    }
    for key in ("missingData", "errors"):
        if final_result.get(key):
            result[key] = final_result[key]
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
    context = dict(payload.get("variables", payload))
    if "asOf" in payload and "asOf" not in context:
        context["asOf"] = payload["asOf"]
    result = run_clinical_flow(args.bundle, context, start_tree_id=args.flow_start_tree_id) if args.flow_start_tree_id else run(args.bundle, args.tree_id, context)
    for key in ("patientId", "encounterId", "contextSnapshotId", "asOf"):
        if key in payload:
            result[key] = payload[key]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
