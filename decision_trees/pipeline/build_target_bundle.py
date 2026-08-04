#!/usr/bin/env python3
"""Build the reviewed target bundle from the five image-based reference flows.

The image files are the extraction evidence for this workspace. This builder is
kept deterministic so that the JSON bundle can be regenerated and audited
without asking an LLM to invent a graph shape.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decision_trees.config.paths import BUNDLE_PATH, IMAGES_DIR


SOURCE_INFO = {
    "image_01_bp_diagnosis": ("01_bp_diagnosis.png", "Sơ đồ chẩn đoán tăng huyết áp"),
    "image_02_bp_thresholds_targets": ("02_bp_thresholds_and_targets.png", "Ngưỡng huyết áp ban đầu và đích điều trị"),
    "image_03_optimized_treatment": ("03_optimized_hypertension_treatment.png", "Sơ đồ điều trị tăng huyết áp tối ưu"),
    "image_04_risk_stratification": ("04_hypertension_risk_stratification.png", "Bảng phân tầng nguy cơ trong tăng huyết áp"),
    "image_05_uncontrolled_resistant": ("05_uncontrolled_resistant_hypertension.png", "Phân loại tăng huyết áp không kiểm soát/kháng trị"),
}


def ref(source_id: str, note: str) -> dict[str, Any]:
    filename, title = SOURCE_INFO[source_id]
    return {
        "sourceId": source_id,
        "page": 1,
        "section": title,
        "tableOrFigure": filename,
        "note": note,
    }


def source_documents() -> list[dict[str, str]]:
    return [
        {
            "id": source_id,
            "title": title,
            "version": "image-reference",
            "localFile": f"decision_trees/images/{filename}",
        }
        for source_id, (filename, title) in SOURCE_INFO.items()
    ]


def variable(
    variable_id: str,
    label: str,
    data_type: str,
    unit: str | None,
    source_system: str,
    source_id: str,
    definition: str,
    *,
    allowed: list[Any] | None = None,
    required: bool = False,
    derived_from: list[str] | None = None,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": variable_id,
        "label": label,
        "dataType": data_type,
        "unit": unit,
        "requiredForEvaluation": required,
        "definition": definition,
        "sourceSystem": source_system,
        "sourceRefs": [ref(source_id, definition)],
    }
    if allowed is not None:
        item["allowedValues"] = allowed
    if derived_from:
        item["derivedFrom"] = derived_from
    if validation:
        item["validation"] = validation
    return item


def predicate(field: str, op: str, value: Any = None) -> dict[str, Any]:
    result = {"field": field, "op": op}
    if op != "present":
        result["value"] = value
    return result


def all_of(*items: dict[str, Any]) -> dict[str, Any]:
    return {"all": list(items)}


def any_of(*items: dict[str, Any]) -> dict[str, Any]:
    return {"any": list(items)}


def display(title: str, detail: str | None = None) -> dict[str, str]:
    result = {"title": title}
    if detail:
        result["detail"] = detail
    return result


def node(
    node_id: str,
    node_type: str,
    title: str,
    source_id: str,
    *,
    detail: str | None = None,
    logic: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    extra_sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": node_id,
        "type": node_type,
        "display": display(title, detail),
        "sourceRefs": [ref(source_id, title)],
    }
    if extra_sources:
        item["sourceRefs"].extend(extra_sources)
    if logic is not None:
        item["logic"] = {"predicate": logic}
    if data is not None:
        item["data"] = data
    return item


def edge(from_id: str, to_id: str, when: str = "default", label: str | None = None) -> dict[str, str]:
    result = {"from": from_id, "to": to_id, "when": when}
    if label:
        result["label"] = label
    return result


def tree(
    tree_id: str,
    name: str,
    purpose: str,
    source_id: str,
    entry_node_id: str,
    input_variables: list[str],
    output_variables: list[str],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, str]],
    *,
    links_to: list[str] | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": tree_id,
        "name": name,
        "purpose": purpose,
        "clinicalStatus": "under_review",
        "entryNodeId": entry_node_id,
        "inputVariables": input_variables,
        "outputVariables": output_variables,
        "linksTo": links_to or [],
        "nodes": nodes,
        "edges": edges,
        "sourceRefs": [ref(source_id, purpose)],
        "notes": notes or ["Được chuyển đổi từ sơ đồ ảnh mục tiêu; cần clinical review trước khi phê duyệt."],
    }


def build_variables() -> list[dict[str, Any]]:
    v: list[dict[str, Any]] = []
    add = v.append
    s1 = "image_01_bp_diagnosis"
    add(variable("bp.measurementMethod", "Phương pháp đo HA xác nhận", "enum", None, "vitals", s1, "Phương pháp dùng sau nhánh đo phòng khám lần 1/lần 2.", allowed=["office_3rd", "home", "abpm_24h"], required=True))
    for prefix, label in (("bp.office1", "HA phòng khám lần 1"), ("bp.office2", "HA phòng khám lần 2"), ("bp.office3", "HA phòng khám lần 3")):
        add(variable(f"{prefix}.systolicMmHg", f"{label} - HATT", "number", "mmHg", "vitals", s1, "Giá trị HATT của lần đo phòng khám tương ứng.", validation={"minimum": 40, "maximum": 300}))
        add(variable(f"{prefix}.diastolicMmHg", f"{label} - HATTr", "number", "mmHg", "vitals", s1, "Giá trị HATTr của lần đo phòng khám tương ứng.", validation={"minimum": 20, "maximum": 200}))
    add(variable("bp.office1.targetOrganDamageOrCvd", "Bằng chứng tổn thương cơ quan đích/bệnh tim mạch ở lần 1", "boolean", None, "clinician_input", s1, "Có bằng chứng tổn thương cơ quan đích hoặc bệnh tim mạch trong đánh giá ban đầu."))
    add(variable("bp.office2.targetOrganDamageOrCvd", "Bằng chứng tổn thương cơ quan đích/bệnh tim mạch ở lần 2", "boolean", None, "clinician_input", s1, "Có bằng chứng tổn thương cơ quan đích do tăng huyết áp hoặc bệnh tim mạch ở lần 2."))
    for prefix, label in (("bp.home", "HA tại nhà"), ("bp.abpm.daytime", "HALT ban ngày"), ("bp.abpm.average24h", "HALT trung bình 24 giờ")):
        add(variable(f"{prefix}.systolicMmHg", f"{label} - HATT", "number", "mmHg", "vitals", s1, "Giá trị HATT của phương pháp đo ngoài phòng khám.", validation={"minimum": 40, "maximum": 300}))
        add(variable(f"{prefix}.diastolicMmHg", f"{label} - HATTr", "number", "mmHg", "vitals", s1, "Giá trị HATTr của phương pháp đo ngoài phòng khám.", validation={"minimum": 20, "maximum": 200}))
    add(variable("bp.category", "Phân loại huyết áp", "enum", None, "derived", s1, "Biến dẫn xuất từ kết quả chẩn đoán hoặc clinical flow.", allowed=["normal", "high_normal", "hypertension", "grade1", "grade2", "hypertensive_crisis", "white_coat_hypertension", "masked_hypertension", "review_required"], derived_from=["bp.office1.systolicMmHg", "bp.office1.diastolicMmHg", "bp.office2.systolicMmHg", "bp.office2.diastolicMmHg", "bp.measurementMethod"], required=False))

    s2 = "image_02_bp_thresholds_targets"
    add(variable("risk.class", "Phân tầng nguy cơ tim mạch", "enum", None, "derived", s2, "Kết quả từ cây phân tầng nguy cơ.", allowed=["low", "medium", "high"], required=False))
    add(variable("treatment.hasHighRiskComorbidity", "Có bệnh đồng mắc/nguy cơ cao", "boolean", None, "derived", s2, "Có BTMXV, đái tháo đường, bệnh thận mạn hoặc bệnh đồng mắc nguy cơ cao.", required=False))
    add(variable("treatment.recommendation", "Khuyến nghị điều trị ban đầu", "enum", None, "derived", s2, "Nhánh điều trị từ ngưỡng HA và nguy cơ.", allowed=["lifestyle_first", "medication_now", "medication_now_high_risk", "review_required"], required=False))
    add(variable("treatment.targetSystolicMmHg", "Đích HATT", "number", "mmHg", "derived", s2, "Đích HATT hiển thị trong sơ đồ mục tiêu.", required=False, validation={"minimum": 80, "maximum": 220}))
    add(variable("treatment.targetDiastolicMmHg", "Đích HATTr", "number", "mmHg", "derived", s2, "Đích HATTr hiển thị trong sơ đồ mục tiêu.", required=False, validation={"minimum": 40, "maximum": 140}))
    add(variable("treatment.controlWindowMonths", "Khoảng thời gian kiểm soát mục tiêu", "enum", "month", "derived", s2, "Khoảng thời gian kiểm soát HA theo nhánh nguy cơ.", allowed=["1-3", "3-6"], required=False))

    s3 = "image_03_optimized_treatment"
    add(variable("patient.ageYears", "Tuổi bệnh nhân", "integer", "year", "patient", s3, "Tuổi bệnh nhân; sơ đồ áp dụng cho người lớn trên 18 tuổi.", validation={"minimum": 0, "maximum": 120}))
    add(variable("bp.assessmentOfficeSystolicMmHg", "HATT phòng khám lúc đánh giá điều trị", "number", "mmHg", "vitals", s3, "HATT phòng khám tại thời điểm bắt đầu flow điều trị tối ưu.", validation={"minimum": 40, "maximum": 300}))
    add(variable("bp.assessmentOfficeDiastolicMmHg", "HATTr phòng khám lúc đánh giá điều trị", "number", "mmHg", "vitals", s3, "HATTr phòng khám tại thời điểm bắt đầu flow điều trị tối ưu.", validation={"minimum": 20, "maximum": 200}))
    for medication_class in ("A", "B", "C", "D", "MRA"):
        add(variable(f"medication.hasClass{medication_class}", f"Đang có nhóm thuốc {medication_class}", "boolean", None, "medication", s3, f"Đang sử dụng nhóm thuốc {medication_class} trong phác đồ."))
    for condition_id, label in (("atheroscleroticCvd", "Bệnh tim mạch do xơ vữa"), ("heartFailure", "Suy tim"), ("stroke", "Tiền sử đột quỵ"), ("ckd", "Bệnh thận mạn"), ("diabetes", "Đái tháo đường")):
        add(variable(f"comorbidity.{condition_id}", label, "boolean", None, "problem_list", s3, f"Có {label.lower()} trong danh sách bệnh đồng mắc."))
    add(variable("treatment.mandatoryIndication", "Có chỉ định điều trị bắt buộc", "boolean", None, "derived", s3, "Biến dẫn xuất từ bệnh mạch vành/xơ vữa, suy tim, đột quỵ, bệnh thận mạn hoặc đái tháo đường.", derived_from=["comorbidity.atheroscleroticCvd", "comorbidity.heartFailure", "comorbidity.stroke", "comorbidity.ckd", "comorbidity.diabetes"]))
    add(variable("medication.agentCount", "Số nhóm thuốc hạ áp", "integer", "class", "medication", s3, "Số nhóm thuốc hạ áp đang sử dụng.", validation={"minimum": 0, "maximum": 10}))
    add(variable("medication.uncontrolledDespiteTripleTherapy", "Chưa kiểm soát dù đã phối hợp ba thuốc", "boolean", None, "clinician_input", s3, "HA vẫn chưa đạt mục tiêu sau phối hợp ba thuốc phù hợp."))
    add(variable("treatment.path", "Nhánh điều trị tối ưu", "enum", None, "derived", s3, "Nhánh được chọn trong sơ đồ điều trị tối ưu.", allowed=["single_pill_strategy", "lifestyle", "mandatory_indication", "initial_combination", "triple_combination", "resistant_referral", "review_required"], required=False))

    s4 = "image_04_risk_stratification"
    add(variable("bp.systolicMmHg", "HATT dùng để phân biệt mức độ trong độ 2", "number", "mmHg", "vitals", s4, "HATT dùng để xác định nhánh độ 2 thấp hay mức từ 180 mmHg trong bảng nguy cơ.", validation={"minimum": 40, "maximum": 300}))
    add(variable("bp.diastolicMmHg", "HATTr dùng để phân biệt mức độ trong độ 2", "number", "mmHg", "vitals", s4, "HATTr dùng để xác định nhánh độ 2 thấp hay mức từ 110 mmHg trong bảng nguy cơ.", validation={"minimum": 20, "maximum": 200}))
    risk_factor_fields = [
        ("ageOver65", "Tuổi ≥65"),
        ("maleSex", "Giới nam"),
        ("heartRateOver80", "Nhịp tim >80 lần/phút"),
        ("overweight", "Thừa cân/béo phì"),
        ("lipidAbnormality", "Rối loạn lipid máu"),
        ("familyHistoryPrematureCvd", "Tiền sử gia đình bệnh tim mạch sớm"),
        ("currentSmoker", "Hút thuốc hiện tại"),
        ("socialEnvironmentalRisk", "Yếu tố xã hội/môi trường bất lợi"),
    ]
    risk_factor_ids: list[str] = []
    for field_name, label in risk_factor_fields:
        field_id = f"risk.{field_name}"
        risk_factor_ids.append(field_id)
        add(variable(field_id, label, "boolean", None, "clinician_input", s4, f"Có {label.lower()} khi phân tầng nguy cơ."))
    add(variable("risk.factorCount", "Số yếu tố nguy cơ", "integer", "factor", "derived", s4, "Số yếu tố nguy cơ được đếm theo bảng phân tầng.", derived_from=risk_factor_ids, validation={"minimum": 0, "maximum": 20}))
    high_risk_fields = [
        ("targetOrganDamage", "Tổn thương cơ quan đích"),
        ("ckdStageAtLeast3", "CKD giai đoạn ≥3"),
        ("diabetes", "Đái tháo đường"),
        ("cardiovascularDisease", "Bệnh tim mạch"),
    ]
    high_risk_ids: list[str] = []
    for field_name, label in high_risk_fields:
        field_id = f"risk.{field_name}"
        high_risk_ids.append(field_id)
        add(variable(field_id, label, "boolean", None, "clinician_input", s4, f"Có {label.lower()} khi phân tầng nguy cơ."))
    add(variable("risk.highRiskComorbidity", "Tổn thương cơ quan đích/bệnh đồng mắc nguy cơ cao", "boolean", None, "derived", s4, "Có tổn thương cơ quan đích, CKD giai đoạn từ 3, đái tháo đường hoặc bệnh tim mạch.", required=False, derived_from=high_risk_ids))

    s5 = "image_05_uncontrolled_resistant"
    add(variable("bp.officeAverageSystolicMmHg", "HATT phòng khám trung bình", "number", "mmHg", "vitals", s5, "HATT phòng khám trung bình trong 2-3 lần đo ngồi.", validation={"minimum": 40, "maximum": 300}))
    add(variable("bp.officeReadingCount", "Số lần đo phòng khám", "integer", "reading", "vitals", s5, "Số lần đo ngồi dùng để tính trung bình phòng khám.", validation={"minimum": 1, "maximum": 5}))
    add(variable("medication.regimenStableWeeks", "Số tuần phác đồ ổn định", "number", "week", "medication", s5, "Thời gian không thay đổi liều/nhóm thuốc gần đây.", validation={"minimum": 0, "maximum": 104}))
    add(variable("medication.includesDiuretic", "Phác đồ có lợi tiểu", "boolean", None, "medication", s5, "Có thiazide, lợi tiểu quai hoặc MRA trong phác đồ."))
    add(variable("resistant.egfrMlMin", "eGFR", "number", "mL/min/1.73m2", "laboratory", s5, "eGFR dùng trong safety and exclusion screen.", validation={"minimum": 0, "maximum": 200}))
    add(variable("resistant.potassiumMmolL", "Kali máu", "number", "mmol/L", "laboratory", s5, "Kali máu dùng trong safety and exclusion screen.", validation={"minimum": 1, "maximum": 10}))
    add(variable("resistant.sodiumMmolL", "Natri máu", "number", "mmol/L", "laboratory", s5, "Natri máu dùng trong safety and exclusion screen.", validation={"minimum": 80, "maximum": 200}))
    add(variable("pregnancy.status", "Tình trạng thai kỳ", "enum", None, "patient", s5, "Thai kỳ là một tiêu chí an toàn cần được kiểm tra.", allowed=["not_pregnant", "pregnant", "postpartum_0_6w", "postpartum_gt_6w", "unknown"]))
    add(variable("resistant.severeLiverDisease", "Bệnh gan nặng", "boolean", None, "problem_list", s5, "Bệnh gan nặng là một tiêu chí an toàn cần được kiểm tra."))
    add(variable("resistant.systolicDropAt12WeeksMmHg", "Mức giảm HATT tại tuần 12", "number", "mmHg", "vitals", s5, "Mức giảm HATT dùng cho điều kiện đạt mục tiêu trong hình (≥8,7 mmHg tại 12 tuần).", validation={"minimum": -200, "maximum": 200}))
    add(variable("resistant.classification", "Phân loại nhánh không kiểm soát/kháng trị", "enum", None, "derived", s5, "Phân loại dựa trên số nhóm thuốc và có lợi tiểu.", allowed=["uncontrolled_two_drug", "resistant_three_or_more_with_diuretic", "add_diuretic_and_reclassify", "review_required"], required=False))
    next(item for item in v if item["id"] == "medication.agentCount")["sourceRefs"].append(ref(s5, "Số nhóm thuốc hạ áp đang sử dụng trong cây 5."))
    add(variable("resistant.treatmentStatus", "Trạng thái điều trị kháng trị", "enum", None, "derived", s5, "Trạng thái sau safety screen.", allowed=["excluded", "eligible", "not_applicable"], required=False))
    add(variable("resistant.drugRecommendation", "Thuốc/hành động xử trí kháng trị", "enum", None, "derived", s5, "Khuyến nghị machine-readable sau safety screen.", allowed=["baxdrostat_1_to_2mg_daily", "address_exclusion_and_retry", "not_started"], required=False))
    add(variable("resistant.followupStatus", "Trạng thái theo dõi", "enum", None, "derived", s5, "Kết quả theo dõi mục tiêu.", allowed=["continue", "escalate_reassess", "not_started"], required=False))
    return v


def collapse_terminal_inferences(tree_item: dict[str, Any]) -> dict[str, Any]:
    """Merge an inference immediately followed by a duplicate terminal node.

    The runtime still needs one terminal outcome, but the extracted graph does
    not need to show the same clinical result twice. The merged terminal keeps
    both machine-readable result/outcome codes, sets, actions and provenance.
    """
    nodes = {node_item["id"]: node_item for node_item in tree_item["nodes"]}
    incoming: dict[str, list[dict[str, str]]] = {node_id: [] for node_id in nodes}
    outgoing: dict[str, list[dict[str, str]]] = {node_id: [] for node_id in nodes}
    for edge_item in tree_item["edges"]:
        incoming[edge_item["to"]].append(edge_item)
        outgoing[edge_item["from"]].append(edge_item)

    removed_end_ids: set[str] = set()
    terminal_aliases: dict[str, str] = {}
    for end_id, end_node in list(nodes.items()):
        if end_node.get("type") != "end":
            continue
        inference_links = [link for link in incoming[end_id] if nodes.get(link["from"], {}).get("type") == "inference"]
        if len(inference_links) != 1:
            continue
        inference = nodes[inference_links[0]["from"]]
        if len(outgoing[inference["id"]]) != 1:
            continue
        inference_data = inference.get("data", {})
        end_data = end_node.get("data", {})
        merged_sets = {**inference_data.get("sets", {}), **end_data.get("sets", {})}
        merged_data = {**inference_data, **end_data}
        if merged_sets:
            merged_data["sets"] = merged_sets
        merged_refs = list(inference.get("sourceRefs", []))
        for source_ref in end_node.get("sourceRefs", []):
            if source_ref not in merged_refs:
                merged_refs.append(source_ref)
        inference["type"] = "end"
        inference["data"] = merged_data
        inference["sourceRefs"] = merged_refs
        removed_end_ids.add(end_id)
        terminal_aliases[end_id] = inference["id"]

    if removed_end_ids:
        tree_item["nodes"] = [node_item for node_item in tree_item["nodes"] if node_item["id"] not in removed_end_ids]
        rewritten_edges = []
        for edge_item in tree_item["edges"]:
            if edge_item["to"] in removed_end_ids:
                inference_id = terminal_aliases[edge_item["to"]]
                if edge_item["from"] == inference_id:
                    continue
                edge_item = {**edge_item, "to": inference_id}
            rewritten_edges.append(edge_item)
        tree_item["edges"] = rewritten_edges
    return tree_item


def build_trees() -> list[dict[str, Any]]:
    s1, s2, s3, s4, s5 = SOURCE_INFO

    bp_nodes = [
        node("bp_start", "start", "Bắt đầu chẩn đoán HA", s1, detail="Đo HA phòng khám lần 1 và khai thác tổn thương cơ quan đích/bệnh tim mạch."),
        node("bp_crisis_gate", "condition", "HA phòng khám lần 1 ≥180/120 và có tổn thương cơ quan đích/bệnh tim mạch?", s1, logic=all_of(any_of(predicate("bp.office1.systolicMmHg", "gte", 180), predicate("bp.office1.diastolicMmHg", "gte", 120)), predicate("bp.office1.targetOrganDamageOrCvd", "eq", True))),
        node("bp_infer_crisis", "inference", "Cơn tăng huyết áp", s1, data={"resultCode": "hypertensive_crisis", "severity": "critical", "sets": {"bp.category": "hypertensive_crisis"}}),
        node("bp_end_crisis", "end", "Cơn THA", s1, data={"outcomeCode": "hypertensive_crisis_detected", "actions": ["Đánh giá cấp cứu và tổn thương cơ quan đích ngay"]}),
        node("bp_second_gate", "condition", "HA phòng khám lần 2 140-179/90-119 và có tổn thương cơ quan đích/bệnh tim mạch?", s1, logic=all_of(any_of(all_of(predicate("bp.office2.systolicMmHg", "gte", 140), predicate("bp.office2.systolicMmHg", "lte", 179)), all_of(predicate("bp.office2.diastolicMmHg", "gte", 90), predicate("bp.office2.diastolicMmHg", "lte", 119))), predicate("bp.office2.targetOrganDamageOrCvd", "eq", True))),
        node("bp_infer_hypertension", "inference", "Tăng huyết áp", s1, data={"resultCode": "hypertension", "severity": "high", "sets": {"bp.category": "hypertension"}}),
        node("bp_end_hypertension", "end", "THA", s1, data={"outcomeCode": "hypertension_detected", "actions": ["Đánh giá nguy cơ và chỉ định điều trị"]}),
        node("bp_method_office", "condition", "Dùng kết quả khám phòng khám lần 3?", s1, logic=predicate("bp.measurementMethod", "eq", "office_3rd")),
        node("bp_office3_normal", "condition", "HATT <130 và HATTr <85?", s1, logic=all_of(predicate("bp.office3.systolicMmHg", "lt", 130), predicate("bp.office3.diastolicMmHg", "lt", 85))),
        node("bp_infer_normal", "inference", "HA bình thường", s1, data={"resultCode": "normal_bp", "severity": "info", "sets": {"bp.category": "normal"}}),
        node("bp_end_normal", "end", "HA bình thường", s1, data={"outcomeCode": "normal_bp"}),
        node("bp_office3_high_normal", "condition", "HATT 130-139 hoặc HATTr 85-89?", s1, logic=any_of(all_of(predicate("bp.office3.systolicMmHg", "gte", 130), predicate("bp.office3.systolicMmHg", "lt", 140)), all_of(predicate("bp.office3.diastolicMmHg", "gte", 85), predicate("bp.office3.diastolicMmHg", "lt", 90)))),
        node("bp_infer_high_normal", "inference", "HA bình thường-cao", s1, data={"resultCode": "high_normal_bp", "severity": "low", "sets": {"bp.category": "high_normal"}}),
        node("bp_end_high_normal", "end", "HA bình thường-cao", s1, data={"outcomeCode": "high_normal_bp"}),
        node("bp_infer_office3_htn", "inference", "Tăng huyết áp", s1, data={"resultCode": "hypertension", "severity": "high", "sets": {"bp.category": "hypertension"}}),
        node("bp_end_office3_htn", "end", "THA", s1, data={"outcomeCode": "hypertension_detected"}),
        node("bp_method_home", "condition", "Dùng kết quả HA tại nhà?", s1, logic=predicate("bp.measurementMethod", "eq", "home")),
        node("bp_home_gate", "condition", "HATT <135 và HATTr <85?", s1, logic=all_of(predicate("bp.home.systolicMmHg", "lt", 135), predicate("bp.home.diastolicMmHg", "lt", 85))),
        node("bp_infer_white_coat_home", "inference", "THA áo choàng trắng/HABT", s1, data={"resultCode": "white_coat_hypertension", "severity": "medium", "sets": {"bp.category": "white_coat_hypertension"}}),
        node("bp_end_white_coat_home", "end", "THA áo choàng trắng/HABT", s1, data={"outcomeCode": "white_coat_hypertension"}),
        node("bp_infer_masked_home", "inference", "THA/THA ẩn", s1, data={"resultCode": "masked_hypertension", "severity": "high", "sets": {"bp.category": "masked_hypertension"}}),
        node("bp_end_masked_home", "end", "THA/THA ẩn", s1, data={"outcomeCode": "masked_hypertension"}),
        node("bp_method_abpm", "condition", "Dùng HALT 24 giờ?", s1, logic=predicate("bp.measurementMethod", "eq", "abpm_24h")),
        node("bp_abpm_gate", "condition", "HA ban ngày <135/85 và/hoặc HA 24h <130/80?", s1, logic=any_of(all_of(predicate("bp.abpm.daytime.systolicMmHg", "lt", 135), predicate("bp.abpm.daytime.diastolicMmHg", "lt", 85)), all_of(predicate("bp.abpm.average24h.systolicMmHg", "lt", 130), predicate("bp.abpm.average24h.diastolicMmHg", "lt", 80)))),
        node("bp_infer_white_coat_abpm", "inference", "THA áo choàng trắng/HABT", s1, data={"resultCode": "white_coat_hypertension", "severity": "medium", "sets": {"bp.category": "white_coat_hypertension"}}),
        node("bp_end_white_coat_abpm", "end", "THA áo choàng trắng/HABT", s1, data={"outcomeCode": "white_coat_hypertension"}),
        node("bp_infer_masked_abpm", "inference", "THA/THA ẩn", s1, data={"resultCode": "masked_hypertension", "severity": "high", "sets": {"bp.category": "masked_hypertension"}}),
        node("bp_end_masked_abpm", "end", "THA/THA ẩn", s1, data={"outcomeCode": "masked_hypertension"}),
        node("bp_end_review", "end", "Cần rà soát dữ liệu đo", s1, data={"resultCode": "bp_diagnosis_review_required", "outcomeCode": "bp_diagnosis_review_required"}),
    ]
    bp_edges = [
        edge("bp_start", "bp_crisis_gate"), edge("bp_crisis_gate", "bp_infer_crisis", "true", "Có"), edge("bp_crisis_gate", "bp_second_gate", "false", "Không"), edge("bp_infer_crisis", "bp_end_crisis"),
        edge("bp_second_gate", "bp_infer_hypertension", "true", "Có"), edge("bp_second_gate", "bp_method_office", "false", "Không"), edge("bp_infer_hypertension", "bp_end_hypertension"),
        edge("bp_method_office", "bp_office3_normal", "true", "HAPK lần 3"), edge("bp_method_office", "bp_method_home", "false", "Không"), edge("bp_office3_normal", "bp_infer_normal", "true", "<130/85"), edge("bp_office3_normal", "bp_office3_high_normal", "false", "Không"), edge("bp_infer_normal", "bp_end_normal"), edge("bp_office3_high_normal", "bp_infer_high_normal", "true", "130-139/85-89"), edge("bp_office3_high_normal", "bp_infer_office3_htn", "false", "≥140/90"), edge("bp_infer_high_normal", "bp_end_high_normal"), edge("bp_infer_office3_htn", "bp_end_office3_htn"),
        edge("bp_method_home", "bp_home_gate", "true", "HATN"), edge("bp_method_home", "bp_method_abpm", "false", "Không"), edge("bp_home_gate", "bp_infer_white_coat_home", "true", "<135/85"), edge("bp_home_gate", "bp_infer_masked_home", "false", "≥135/85"), edge("bp_infer_white_coat_home", "bp_end_white_coat_home"), edge("bp_infer_masked_home", "bp_end_masked_home"),
        edge("bp_method_abpm", "bp_abpm_gate", "true", "HALT 24h"), edge("bp_method_abpm", "bp_end_review", "false", "Chưa chọn phương pháp"), edge("bp_abpm_gate", "bp_infer_white_coat_abpm", "true", "Đạt ngưỡng thấp"), edge("bp_abpm_gate", "bp_infer_masked_abpm", "false", "Không đạt"), edge("bp_infer_white_coat_abpm", "bp_end_white_coat_abpm"), edge("bp_infer_masked_abpm", "bp_end_masked_abpm"),
    ]

    threshold_nodes = [
        node("threshold_start", "start", "Ngưỡng HA và đích điều trị", s2, detail="Phân biệt HA bình thường-cao và THA ở người lớn."),
        node("threshold_high_normal", "condition", "HA bình thường-cao 130-139/85-89?", s2, logic=predicate("bp.category", "eq", "high_normal")),
        node("threshold_high_normal_risk", "condition", "Nguy cơ cao/bệnh đồng mắc nguy cơ cao?", s2, logic=any_of(predicate("risk.class", "eq", "high"), predicate("treatment.hasHighRiskComorbidity", "eq", True))),
        node("threshold_infer_high_risk", "inference", "Điều trị thuốc ở bệnh nhân nguy cơ cao", s2, detail="Điều trị thuốc theo cá thể hóa và nguy cơ; đích <130/80 mmHg.", data={"resultCode": "high_normal_high_risk_treatment", "severity": "high", "sets": {"treatment.recommendation": "medication_now_high_risk", "treatment.targetSystolicMmHg": 130, "treatment.targetDiastolicMmHg": 80, "treatment.controlWindowMonths": "3-6"}}),
        node("threshold_end_high_risk", "end", "Điều trị nguy cơ cao", s2, data={"outcomeCode": "high_normal_high_risk_treatment_started"}),
        node("threshold_infer_lifestyle", "inference", "Thay đổi lối sống", s2, detail="HA bình thường-cao, nguy cơ thấp/trung bình.", data={"resultCode": "high_normal_lifestyle", "severity": "low", "sets": {"treatment.recommendation": "lifestyle_first", "treatment.targetSystolicMmHg": 130, "treatment.targetDiastolicMmHg": 80, "treatment.controlWindowMonths": "3-6"}}),
        node("threshold_end_lifestyle", "end", "Theo dõi sau thay đổi lối sống", s2, data={"outcomeCode": "high_normal_lifestyle_followup"}),
        node("threshold_hypertension", "condition", "THA HATT ≥140 và/hoặc HATTr ≥90?", s2, logic=predicate("bp.category", "in", ["hypertension", "grade1", "grade2"])),
        node("threshold_htn_risk", "condition", "Có bệnh đồng mắc/nguy cơ cao?", s2, logic=any_of(predicate("risk.class", "eq", "high"), predicate("treatment.hasHighRiskComorbidity", "eq", True))),
        node("threshold_infer_htn_high", "inference", "Điều trị thuốc ngay - nguy cơ cao", s2, detail="Thay đổi lối sống; đích <130/80 mmHg khi dung nạp.", data={"resultCode": "hypertension_high_risk_medication", "severity": "high", "sets": {"treatment.recommendation": "medication_now_high_risk", "treatment.targetSystolicMmHg": 130, "treatment.targetDiastolicMmHg": 80, "treatment.controlWindowMonths": "1-3"}}),
        node("threshold_end_htn_high", "end", "Điều trị THA nguy cơ cao", s2, data={"outcomeCode": "hypertension_high_risk_treatment_started"}),
        node("threshold_infer_htn_standard", "inference", "Điều trị thuốc ngay", s2, detail="THA không có bệnh đồng mắc: đích HATT <140 và HATTr khoảng <80.", data={"resultCode": "hypertension_medication_start", "severity": "high", "sets": {"treatment.recommendation": "medication_now", "treatment.targetSystolicMmHg": 140, "treatment.targetDiastolicMmHg": 80, "treatment.controlWindowMonths": "3-6"}}),
        node("threshold_end_htn_standard", "end", "Điều trị THA", s2, data={"outcomeCode": "hypertension_treatment_started"}),
        node("threshold_end_review", "end", "Cần rà soát phân loại HA", s2, data={"resultCode": "threshold_review_required", "outcomeCode": "threshold_review_required"}),
    ]
    threshold_edges = [
        edge("threshold_start", "threshold_high_normal"), edge("threshold_high_normal", "threshold_high_normal_risk", "true", "Có"), edge("threshold_high_normal", "threshold_hypertension", "false", "Không"), edge("threshold_high_normal_risk", "threshold_infer_high_risk", "true", "Có"), edge("threshold_high_normal_risk", "threshold_infer_lifestyle", "false", "Không"), edge("threshold_infer_high_risk", "threshold_end_high_risk"), edge("threshold_infer_lifestyle", "threshold_end_lifestyle"),
        edge("threshold_hypertension", "threshold_htn_risk", "true", "Có"), edge("threshold_hypertension", "threshold_end_review", "false", "Không"), edge("threshold_htn_risk", "threshold_infer_htn_high", "true", "Có"), edge("threshold_htn_risk", "threshold_infer_htn_standard", "false", "Không"), edge("threshold_infer_htn_high", "threshold_end_htn_high"), edge("threshold_infer_htn_standard", "threshold_end_htn_standard"),
    ]

    optimized_nodes = [
        node("optimized_start", "start", "Điều trị tăng huyết áp tối ưu", s3, detail="HA phòng khám ≥130/85 mmHg ở người lớn >18 tuổi; khám toàn diện và đánh giá nguy cơ."),
        node("optimized_entry_gate", "condition", "Người lớn >18 tuổi và HA phòng khám ≥130/85?", s3, logic=all_of(predicate("patient.ageYears", "gt", 18), any_of(predicate("bp.assessmentOfficeSystolicMmHg", "gte", 130), predicate("bp.assessmentOfficeDiastolicMmHg", "gte", 85)))),
        node("optimized_low_risk_high_normal", "condition", "HA bình thường-cao và nguy cơ thấp/trung bình?", s3, logic=all_of(predicate("bp.category", "eq", "high_normal"), predicate("treatment.hasHighRiskComorbidity", "eq", False))),
        node("optimized_infer_lifestyle", "inference", "Một viên A/B/C/D", s3, detail="Khởi trị một viên theo cá thể hóa và nguy cơ.", data={"resultCode": "optimized_single_pill_strategy", "severity": "medium", "sets": {"treatment.path": "single_pill_strategy"}}),
        node("optimized_end_lifestyle", "end", "Theo dõi sau khởi trị một viên", s3, data={"outcomeCode": "optimized_single_pill_followup"}),
        node("optimized_mandatory", "condition", "Có chỉ định điều trị bắt buộc?", s3, detail="Bệnh mạch vành, suy tim, bệnh thận mạn, đái tháo đường hoặc chỉ định bắt buộc khác.", logic=predicate("treatment.mandatoryIndication", "eq", True)),
        node("optimized_infer_mandatory", "inference", "Điều trị theo bệnh đồng mắc", s3, data={"resultCode": "mandatory_indication_treatment", "severity": "high", "sets": {"treatment.path": "mandatory_indication"}}),
        node("optimized_end_mandatory", "end", "Điều trị theo chỉ định bắt buộc", s3, data={"outcomeCode": "mandatory_indication_treatment_started"}),
        node("optimized_htn_gate", "condition", "Nguy cơ cao với HA bình thường-cao hoặc THA cần điều trị phối hợp?", s3, logic=any_of(all_of(predicate("bp.category", "eq", "high_normal"), predicate("treatment.hasHighRiskComorbidity", "eq", True)), predicate("bp.category", "in", ["hypertension", "grade1", "grade2"]))),
        node("optimized_infer_combo", "inference", "Viên phối hợp A+C hoặc D liều thấp", s3, data={"resultCode": "initial_combination_started", "severity": "high", "sets": {"treatment.path": "initial_combination"}}),
        node("optimized_agent_count_present", "condition", "Đã biết số nhóm thuốc đang dùng?", s3, logic=predicate("medication.agentCount", "present")),
        node("optimized_triple_gate", "condition", "Đã cần phối hợp ≥3 nhóm thuốc?", s3, logic=predicate("medication.agentCount", "gte", 3)),
        node("optimized_infer_triple", "inference", "Viên phối hợp A+C+D", s3, data={"resultCode": "triple_combination_started", "severity": "high", "sets": {"treatment.path": "triple_combination"}}),
        node("optimized_uncontrolled_gate", "condition", "Vẫn chưa kiểm soát sau phối hợp ba thuốc?", s3, logic=predicate("medication.uncontrolledDespiteTripleTherapy", "eq", True)),
        node("optimized_infer_resistant", "inference", "THA kháng trị - chuyển đánh giá chuyên khoa", s3, detail="Thêm MRA hoặc thuốc phù hợp và đánh giá theo cây không kiểm soát/kháng trị.", data={"resultCode": "resistant_htn_referral", "severity": "high", "sets": {"treatment.path": "resistant_referral"}}, extra_sources=[ref(s5, "Nhánh chuyển sang flow không kiểm soát/kháng trị")]),
        node("optimized_link_resistant", "link", "Chuyển cây không kiểm soát/kháng trị", s3, data={"targetTreeId": "uncontrolled_resistant_hypertension", "callMode": "subtree", "passContext": True, "returnPolicy": "merge_context"}, extra_sources=[ref(s5, "Cây mục tiêu cho nhánh kháng trị")]),
        node("optimized_end_triple", "end", "Theo dõi sau phối hợp ba thuốc", s3, data={"resultCode": "triple_combination_followup", "outcomeCode": "triple_combination_followup"}),
        node("optimized_end_combo", "end", "Theo dõi sau khởi trị phối hợp", s3, data={"resultCode": "initial_combination_followup", "outcomeCode": "initial_combination_followup"}),
        node("optimized_end_review", "end", "Chưa đủ dữ liệu chọn nhánh điều trị", s3, data={"resultCode": "optimized_treatment_review_required", "outcomeCode": "optimized_treatment_review_required"}),
    ]
    optimized_edges = [
        edge("optimized_start", "optimized_entry_gate"), edge("optimized_entry_gate", "optimized_low_risk_high_normal", "true", "Có"), edge("optimized_entry_gate", "optimized_end_review", "false", "Không"), edge("optimized_low_risk_high_normal", "optimized_infer_lifestyle", "true", "Có"), edge("optimized_low_risk_high_normal", "optimized_mandatory", "false", "Không"), edge("optimized_infer_lifestyle", "optimized_end_lifestyle"), edge("optimized_mandatory", "optimized_infer_mandatory", "true", "Có"), edge("optimized_mandatory", "optimized_htn_gate", "false", "Không"), edge("optimized_infer_mandatory", "optimized_end_mandatory"), edge("optimized_htn_gate", "optimized_agent_count_present", "true", "Có"), edge("optimized_htn_gate", "optimized_end_review", "false", "Không"), edge("optimized_agent_count_present", "optimized_triple_gate", "true", "Đã biết"), edge("optimized_agent_count_present", "optimized_infer_combo", "false", "Chưa biết"), edge("optimized_infer_combo", "optimized_end_combo"), edge("optimized_triple_gate", "optimized_infer_triple", "true", "Có"), edge("optimized_triple_gate", "optimized_end_combo", "false", "Chưa"), edge("optimized_infer_triple", "optimized_uncontrolled_gate"), edge("optimized_uncontrolled_gate", "optimized_infer_resistant", "true", "Có"), edge("optimized_uncontrolled_gate", "optimized_end_triple", "false", "Không"), edge("optimized_infer_resistant", "optimized_link_resistant"),
    ]

    risk_nodes = [
        node("risk_start", "start", "Phân tầng nguy cơ tim mạch", s4, detail="Tra bảng theo phân loại HA, số yếu tố nguy cơ và bệnh đồng mắc/tổn thương cơ quan đích."),
        node("risk_high_comorbidity", "condition", "Có TOD/CKD ≥3/ĐTĐ/bệnh tim mạch?", s4, logic=predicate("risk.highRiskComorbidity", "eq", True)),
        node("risk_infer_high_comorbidity", "inference", "Nguy cơ cao", s4, data={"resultCode": "risk_high", "severity": "high", "sets": {"risk.class": "high"}}),
        node("risk_end_high_comorbidity", "end", "Nguy cơ cao", s4, data={"outcomeCode": "risk_high"}),
        node("risk_grade2", "condition", "HA độ 2?", s4, logic=predicate("bp.category", "eq", "grade2")),
        node("risk_grade2_high_band", "condition", "Độ 2 mức HATT ≥180 hoặc HATTr ≥110?", s4, logic=any_of(predicate("bp.systolicMmHg", "gte", 180), predicate("bp.diastolicMmHg", "gte", 110))),
        node("risk_grade2_factors", "condition", "Có ít nhất 1 yếu tố nguy cơ?", s4, logic=predicate("risk.factorCount", "gte", 1)),
        node("risk_infer_high_grade2", "inference", "Nguy cơ cao", s4, data={"resultCode": "risk_high", "severity": "high", "sets": {"risk.class": "high"}}),
        node("risk_infer_medium_grade2", "inference", "Nguy cơ trung bình", s4, data={"resultCode": "risk_medium", "severity": "medium", "sets": {"risk.class": "medium"}}),
        node("risk_end_high_grade2", "end", "Nguy cơ cao", s4, data={"outcomeCode": "risk_high"}),
        node("risk_end_medium_grade2", "end", "Nguy cơ trung bình", s4, data={"outcomeCode": "risk_medium"}),
        node("risk_grade1", "condition", "HA độ 1?", s4, logic=predicate("bp.category", "eq", "grade1")),
        node("risk_grade1_three", "condition", "Có ≥3 yếu tố nguy cơ?", s4, logic=predicate("risk.factorCount", "gte", 3)),
        node("risk_infer_high_grade1", "inference", "Nguy cơ cao", s4, data={"resultCode": "risk_high", "severity": "high", "sets": {"risk.class": "high"}}),
        node("risk_grade1_one", "condition", "Có ít nhất 1 yếu tố nguy cơ?", s4, logic=predicate("risk.factorCount", "gte", 1)),
        node("risk_infer_medium_grade1", "inference", "Nguy cơ trung bình", s4, data={"resultCode": "risk_medium", "severity": "medium", "sets": {"risk.class": "medium"}}),
        node("risk_infer_low_grade1", "inference", "Nguy cơ thấp", s4, data={"resultCode": "risk_low", "severity": "low", "sets": {"risk.class": "low"}}),
        node("risk_end_high_grade1", "end", "Nguy cơ cao", s4, data={"outcomeCode": "risk_high"}),
        node("risk_end_medium_grade1", "end", "Nguy cơ trung bình", s4, data={"outcomeCode": "risk_medium"}),
        node("risk_end_low_grade1", "end", "Nguy cơ thấp", s4, data={"outcomeCode": "risk_low"}),
        node("risk_high_normal", "condition", "HA bình thường-cao?", s4, logic=predicate("bp.category", "eq", "high_normal")),
        node("risk_high_normal_three", "condition", "Có ≥3 yếu tố nguy cơ?", s4, logic=predicate("risk.factorCount", "gte", 3)),
        node("risk_infer_medium_high_normal", "inference", "Nguy cơ trung bình", s4, data={"resultCode": "risk_medium", "severity": "medium", "sets": {"risk.class": "medium"}}),
        node("risk_infer_low_high_normal", "inference", "Nguy cơ thấp", s4, data={"resultCode": "risk_low", "severity": "low", "sets": {"risk.class": "low"}}),
        node("risk_end_medium_high_normal", "end", "Nguy cơ trung bình", s4, data={"outcomeCode": "risk_medium"}),
        node("risk_end_low_high_normal", "end", "Nguy cơ thấp", s4, data={"outcomeCode": "risk_low"}),
        node("risk_normal", "condition", "HA bình thường?", s4, logic=predicate("bp.category", "eq", "normal")),
        node("risk_infer_low_normal", "inference", "Nguy cơ thấp", s4, data={"resultCode": "risk_low", "severity": "low", "sets": {"risk.class": "low"}}),
        node("risk_end_low_normal", "end", "Nguy cơ thấp", s4, data={"outcomeCode": "risk_low"}),
        node("risk_end_review", "end", "Cần rà soát phân loại nguy cơ", s4, data={"resultCode": "risk_review_required", "outcomeCode": "risk_review_required"}),
    ]
    risk_edges = [
        edge("risk_start", "risk_high_comorbidity"), edge("risk_high_comorbidity", "risk_infer_high_comorbidity", "true", "Có"), edge("risk_high_comorbidity", "risk_grade2", "false", "Không"), edge("risk_infer_high_comorbidity", "risk_end_high_comorbidity"), edge("risk_grade2", "risk_grade2_high_band", "true", "Có"), edge("risk_grade2", "risk_grade1", "false", "Không"), edge("risk_grade2_high_band", "risk_infer_high_grade2", "true", "≥180/110"), edge("risk_grade2_high_band", "risk_grade2_factors", "false", "160-179/100-109"), edge("risk_grade2_factors", "risk_infer_high_grade2", "true", "Có YTNC"), edge("risk_grade2_factors", "risk_infer_medium_grade2", "false", "Không YTNC"), edge("risk_infer_high_grade2", "risk_end_high_grade2"), edge("risk_infer_medium_grade2", "risk_end_medium_grade2"), edge("risk_grade1", "risk_grade1_three", "true", "Có"), edge("risk_grade1", "risk_high_normal", "false", "Không"), edge("risk_grade1_three", "risk_infer_high_grade1", "true", "≥3"), edge("risk_grade1_three", "risk_grade1_one", "false", "<3"), edge("risk_infer_high_grade1", "risk_end_high_grade1"), edge("risk_grade1_one", "risk_infer_medium_grade1", "true", "1-2"), edge("risk_grade1_one", "risk_infer_low_grade1", "false", "0"), edge("risk_infer_medium_grade1", "risk_end_medium_grade1"), edge("risk_infer_low_grade1", "risk_end_low_grade1"), edge("risk_high_normal", "risk_high_normal_three", "true", "Có"), edge("risk_high_normal", "risk_normal", "false", "Không"), edge("risk_high_normal_three", "risk_infer_medium_high_normal", "true", "≥3"), edge("risk_high_normal_three", "risk_infer_low_high_normal", "false", "<3"), edge("risk_infer_medium_high_normal", "risk_end_medium_high_normal"), edge("risk_infer_low_high_normal", "risk_end_low_high_normal"), edge("risk_normal", "risk_infer_low_normal", "true", "Có"), edge("risk_normal", "risk_end_review", "false", "Không"), edge("risk_infer_low_normal", "risk_end_low_normal"),
    ]

    resistant_nodes = [
        node("resistant_start", "start", "Hypertension General — Phân loại THA", s5, detail="Root"),
        node("resistant_range", "condition", "Seated SBP 140–169 mmHg?", s5, detail="Office average, 2–3 readings", logic=all_of(predicate("bp.officeAverageSystolicMmHg", "gte", 140), predicate("bp.officeAverageSystolicMmHg", "lte", 169), predicate("bp.officeReadingCount", "in", [2, 3]))),
        node("resistant_end_out_of_range", "end", "Out of Range — Cần đánh giá thêm", s5, detail="Manage first", data={"resultCode": "resistant_out_of_range", "outcomeCode": "resistant_out_of_range_manage_first"}),
        node("resistant_stable", "condition", "Phác đồ ổn định ≥ 4 tuần?", s5, detail="No dose changes in past month", logic=predicate("medication.regimenStableWeeks", "gte", 4)),
        node("resistant_end_defer", "end", "Defer — Đánh giá lại sau", s5, detail="Re-assess later", data={"resultCode": "resistant_defer", "outcomeCode": "resistant_defer_reassess"}),
        node("resistant_agent_count", "condition", "Số nhóm thuốc hạ áp đang dùng?", s5, detail="Including drug classes", logic=predicate("medication.agentCount", "eq", 2)),
        node("resistant_agent_count_ge3", "condition", "Số nhóm thuốc ≥3?", s5, detail="Chỉ chấp nhận đúng 2 hoặc từ 3 nhóm thuốc trở lên.", logic=predicate("medication.agentCount", "gte", 3)),
        node("resistant_end_agent_count_review", "end", "Cần rà soát số nhóm thuốc", s5, detail="Giá trị phải là đúng 2 hoặc ≥3.", data={"resultCode": "resistant_agent_count_review_required", "outcomeCode": "resistant_agent_count_review_required", "sets": {"resistant.classification": "review_required"}}),
        node("resistant_infer_uncontrolled", "inference", "Uncontrolled HTN — Phác đồ 2 thuốc", s5, detail="2-drug regimen", data={"resultCode": "uncontrolled_htn_arm", "severity": "high", "sets": {"resistant.classification": "uncontrolled_two_drug"}}),
        node("resistant_diuretic", "condition", "Phác đồ có lợi tiểu?", s5, detail="Thiazide, lợi tiểu quai hoặc MRA", logic=predicate("medication.includesDiuretic", "eq", True)),
        node("resistant_infer_resistant", "inference", "Resistant HTN — ≥3 thuốc + lợi tiểu", s5, detail="≥3 drugs + diuretic", data={"resultCode": "resistant_htn_arm", "severity": "critical", "sets": {"resistant.classification": "resistant_three_or_more_with_diuretic"}}),
        node("resistant_end_add_diuretic", "end", "Thêm lợi tiểu — Phân loại lại sau", s5, detail="Re-classify later", data={"resultCode": "add_diuretic", "outcomeCode": "add_diuretic_reclassify", "sets": {"resistant.classification": "add_diuretic_and_reclassify"}}),
        node("resistant_safety_screen", "inference", "Safety & exclusion screen", s5, detail="eGFR, K+, Na+, pregnancy, liver", data={"resultCode": "resistant_safety_screen_started"}),
        node("resistant_safety_data", "condition", "Đủ dữ liệu safety screen?", s5, detail="eGFR, K+, Na+, pregnancy và bệnh gan phải được cung cấp trước khi phân loại.", logic=all_of(predicate("resistant.egfrMlMin", "present"), predicate("resistant.potassiumMmolL", "present"), predicate("resistant.sodiumMmolL", "present"), predicate("pregnancy.status", "present"), predicate("resistant.severeLiverDisease", "present"))),
        node("resistant_end_safety_data_review", "end", "Cần bổ sung dữ liệu safety screen", s5, detail="Không tự động kết luận khi thiếu eGFR, K+, Na+, thai kỳ hoặc bệnh gan.", data={"resultCode": "resistant_safety_data_required", "outcomeCode": "resistant_safety_data_required", "sets": {"resistant.treatmentStatus": "not_started", "resistant.drugRecommendation": "not_started"}}),
        node("resistant_exclusion", "condition", "Any exclusion criteria present?", s5, detail="K+ >5.5, eGFR <30, pregnancy...", logic=any_of(predicate("resistant.egfrMlMin", "lt", 30), predicate("resistant.potassiumMmolL", "gt", 5.5), predicate("pregnancy.status", "in", ["pregnant", "postpartum_0_6w"]), predicate("resistant.severeLiverDisease", "eq", True))),
        node("resistant_end_excluded", "end", "Excluded — Xử trí và thử lại", s5, detail="Address & retry", data={"resultCode": "resistant_excluded", "outcomeCode": "resistant_excluded_address_and_retry", "sets": {"resistant.treatmentStatus": "excluded", "resistant.drugRecommendation": "address_exclusion_and_retry"}}),
        node("resistant_infer_eligible", "inference", "Eligible for baxdrostat", s5, detail="1–2 mg once daily, add to regimen", data={"resultCode": "resistant_treatment_eligible", "severity": "high", "sets": {"resistant.treatmentStatus": "eligible", "resistant.drugRecommendation": "baxdrostat_1_to_2mg_daily"}}),
        node("resistant_infer_monitor", "inference", "Monitor electrolytes & BP", s5, detail="Baseline, wks 1–2, 4, 12", data={"resultCode": "resistant_monitoring_started"}),
        node("resistant_target", "condition", "Target met?", s5, detail="SBP drop ≥8.7 mmHg at 12 wks", logic=predicate("resistant.systolicDropAt12WeeksMmHg", "gte", 8.7)),
        node("resistant_end_continue", "end", "Continue therapy", s5, detail="SBP drop ≥8.7 mmHg at 12 wks", data={"resultCode": "resistant_continue_therapy", "outcomeCode": "resistant_target_met", "sets": {"resistant.followupStatus": "continue"}}),
        node("resistant_end_escalate", "end", "Escalate / reassess", s5, detail="Dose adjust or refer", data={"resultCode": "resistant_escalate_reassess", "outcomeCode": "resistant_target_not_met", "sets": {"resistant.followupStatus": "escalate_reassess"}}),
    ]
    resistant_edges = [
        edge("resistant_start", "resistant_range"), edge("resistant_range", "resistant_end_out_of_range", "false", "No — ngoài khoảng"), edge("resistant_range", "resistant_stable", "true", "Yes — SBP 140–169 mmHg"), edge("resistant_stable", "resistant_end_defer", "false", "No — phác đồ chưa ổn định"), edge("resistant_stable", "resistant_agent_count", "true", "Yes — phác đồ ổn định"), edge("resistant_agent_count", "resistant_infer_uncontrolled", "true", "Exactly 2"), edge("resistant_agent_count", "resistant_agent_count_ge3", "false", "Không phải 2"), edge("resistant_agent_count_ge3", "resistant_diuretic", "true", "≥ 3"), edge("resistant_agent_count_ge3", "resistant_end_agent_count_review", "false", "< 2 — rà soát"), edge("resistant_diuretic", "resistant_infer_resistant", "true", "Yes"), edge("resistant_diuretic", "resistant_end_add_diuretic", "false", "No"), edge("resistant_infer_uncontrolled", "resistant_safety_screen", "default", "Both arms"), edge("resistant_infer_resistant", "resistant_safety_screen", "default", "Both arms"), edge("resistant_safety_screen", "resistant_safety_data", "default"), edge("resistant_safety_data", "resistant_exclusion", "true", "Đủ dữ liệu"), edge("resistant_safety_data", "resistant_end_safety_data_review", "false", "Thiếu dữ liệu"), edge("resistant_exclusion", "resistant_end_excluded", "true", "Yes"), edge("resistant_exclusion", "resistant_infer_eligible", "false", "No"), edge("resistant_infer_eligible", "resistant_infer_monitor"), edge("resistant_infer_monitor", "resistant_target"), edge("resistant_target", "resistant_end_continue", "true", "Target met"), edge("resistant_target", "resistant_end_escalate", "false", "Not met"),
    ]

    trees = [
        tree("bp_diagnosis", "BP Diagnosis Tree", "Chẩn đoán tăng huyết áp bằng đo phòng khám, HATN và HALT.", s1, "bp_start", ["bp.measurementMethod", "bp.office1.systolicMmHg", "bp.office1.diastolicMmHg", "bp.office1.targetOrganDamageOrCvd", "bp.office2.systolicMmHg", "bp.office2.diastolicMmHg", "bp.office2.targetOrganDamageOrCvd", "bp.office3.systolicMmHg", "bp.office3.diastolicMmHg", "bp.home.systolicMmHg", "bp.home.diastolicMmHg", "bp.abpm.daytime.systolicMmHg", "bp.abpm.daytime.diastolicMmHg", "bp.abpm.average24h.systolicMmHg", "bp.abpm.average24h.diastolicMmHg"], ["bp.category"], bp_nodes, bp_edges),
        tree("bp_thresholds_targets", "BP Thresholds and Targets Tree", "Chọn chiến lược thay đổi lối sống, điều trị thuốc và đích HA theo ngưỡng/nguy cơ.", s2, "threshold_start", ["bp.category", "risk.class", "treatment.hasHighRiskComorbidity"], ["treatment.recommendation", "treatment.targetSystolicMmHg", "treatment.targetDiastolicMmHg", "treatment.controlWindowMonths"], threshold_nodes, threshold_edges),
        tree("optimized_hypertension_treatment", "Optimized Hypertension Treatment Tree", "Điều trị tăng huyết áp tối ưu bằng thay đổi lối sống, phối hợp thuốc và chuyển đánh giá kháng trị.", s3, "optimized_start", ["patient.ageYears", "bp.assessmentOfficeSystolicMmHg", "bp.assessmentOfficeDiastolicMmHg", "bp.category", "treatment.hasHighRiskComorbidity", "treatment.mandatoryIndication", "medication.agentCount", "medication.uncontrolledDespiteTripleTherapy", "medication.hasClassA", "medication.hasClassB", "medication.hasClassC", "medication.hasClassD", "medication.hasClassMRA", "comorbidity.atheroscleroticCvd", "comorbidity.heartFailure", "comorbidity.stroke", "comorbidity.ckd", "comorbidity.diabetes"], ["treatment.path"], optimized_nodes, optimized_edges, links_to=["uncontrolled_resistant_hypertension"]),
        tree("hypertension_risk_stratification", "Hypertension Risk Stratification Tree", "Phân tầng nguy cơ theo bảng nguy cơ trong năm nhóm phân loại.", s4, "risk_start", ["bp.category", "bp.systolicMmHg", "bp.diastolicMmHg", "risk.factorCount", "risk.ageOver65", "risk.maleSex", "risk.heartRateOver80", "risk.overweight", "risk.lipidAbnormality", "risk.familyHistoryPrematureCvd", "risk.currentSmoker", "risk.socialEnvironmentalRisk", "risk.highRiskComorbidity", "risk.targetOrganDamage", "risk.ckdStageAtLeast3", "risk.diabetes", "risk.cardiovascularDisease"], ["risk.class"], risk_nodes, risk_edges),
        tree("uncontrolled_resistant_hypertension", "Hypertension General — Phân loại THA", "Phân loại đầy đủ nhánh không kiểm soát/kháng trị, safety screen, điều trị và theo dõi theo ảnh cây 5.", s5, "resistant_start", ["bp.officeAverageSystolicMmHg", "bp.officeReadingCount", "medication.regimenStableWeeks", "medication.agentCount", "medication.includesDiuretic", "resistant.egfrMlMin", "resistant.potassiumMmolL", "resistant.sodiumMmolL", "pregnancy.status", "resistant.severeLiverDisease", "resistant.systolicDropAt12WeeksMmHg"], ["resistant.classification", "resistant.treatmentStatus", "resistant.drugRecommendation", "resistant.followupStatus"], resistant_nodes, resistant_edges),
    ]
    return [collapse_terminal_inferences(tree_item) for tree_item in trees]


def main() -> None:
    bundle = {
        "formatVersion": "decision-tree-bundle.v1",
        "bundleId": "vsh-vnha-2022-image-targets",
        "bundleVersion": "0.2.0",
        "locale": "vi-VN",
        "clinicalStatus": "under_review",
        "clinicalReviewRequired": True,
        "sourceDocuments": source_documents(),
        "variables": build_variables(),
        "trees": build_trees(),
    }
    BUNDLE_PATH.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "bundle": str(BUNDLE_PATH), "trees": len(bundle["trees"]), "variables": len(bundle["variables"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
