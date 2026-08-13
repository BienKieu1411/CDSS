const fs = require("fs");

const bundlePath = "decision_trees/bundle/decision_tree_bundle.json";
const variablesPath = "decision_trees/contracts/clinical_variables.json";
const triggersPath = "decision_trees/contracts/trigger_registry.json";

function readJson(path) {
  return JSON.parse(fs.readFileSync(path, "utf8"));
}

function writeJson(path, value) {
  fs.writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
}

function removeKeys(value, keys) {
  if (!value || typeof value !== "object") return;
  if (Array.isArray(value)) {
    for (let index = value.length - 1; index >= 0; index -= 1) {
      if (typeof value[index] === "string" && keys.has(value[index])) value.splice(index, 1);
      else if (value[index] && typeof value[index] === "object" && keys.has(value[index].variableId)) value.splice(index, 1);
      else removeKeys(value[index], keys);
    }
    return;
  }
  if (keys.has(value.variableId)) {
    for (const key of Object.keys(value)) delete value[key];
    return;
  }
  for (const key of Object.keys(value)) {
    if (keys.has(key)) delete value[key];
    else removeKeys(value[key], keys);
  }
}

function removeStringValues(value, values) {
  if (!value || typeof value !== "object") return;
  if (Array.isArray(value)) {
    for (let index = value.length - 1; index >= 0; index -= 1) {
      if (typeof value[index] === "string" && values.has(value[index])) value.splice(index, 1);
      else removeStringValues(value[index], values);
    }
    return;
  }
  for (const [key, child] of Object.entries(value)) {
    if (typeof child === "string" && values.has(child)) delete value[key];
    else removeStringValues(child, values);
  }
}

function formatOutputValue(value) {
  if (typeof value === "string") return value;
  if (value === null) return "null";
  if (Array.isArray(value) || typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function outputAssignments(node) {
  const sets = node?.data?.sets;
  if (!sets || typeof sets !== "object" || Array.isArray(sets)) return "";
  return Object.entries(sets)
    .map(([field, value]) => `${field} = ${formatOutputValue(value)}`)
    .join("\n");
}

function normalizeOutputDisplays(tree) {
  for (const node of tree.nodes || []) {
    if (!["inference", "end"].includes(node.type)) continue;
    const assignments = outputAssignments(node);
    if (!assignments) continue;
    node.display = {
      ...node.display,
      detail: assignments,
    };
  }
}

function ensureVariable(bundle, variable) {
  const index = bundle.variables.findIndex((item) => item.id === variable.id);
  if (index >= 0) bundle.variables[index] = { ...bundle.variables[index], ...variable };
  else bundle.variables.push(variable);
}

function nodeById(tree, id) {
  return tree.nodes.find((node) => node.id === id);
}

function edge(tree, from, to) {
  return tree.edges.find((item) => item.from === from && item.to === to);
}

function setLabel(tree, from, to, label) {
  const item = edge(tree, from, to);
  if (item) item.label = label;
}

function replaceEdge(tree, from, targets, value) {
  const targetSet = new Set(targets);
  tree.edges = tree.edges.filter((item) => !(item.from === from && targetSet.has(item.to)));
  tree.edges.push(value);
}

function addPredicateToAny(node, predicate) {
  const current = node?.logic?.predicate;
  if (!current || !Array.isArray(current.any)) return;
  const exists = current.any.some(
    (item) => item.field === predicate.field && item.op === predicate.op && item.value === predicate.value,
  );
  if (!exists) current.any.push(predicate);
}

function replaceField(value, from, to) {
  if (!value || typeof value !== "object") return;
  if (Array.isArray(value)) {
    value.forEach((item) => replaceField(item, from, to));
    return;
  }
  if (value.field === from) value.field = to;
  for (const child of Object.values(value)) replaceField(child, from, to);
}

function rewritePredicate(value, transform) {
  if (!value || typeof value !== "object") return;
  if (Array.isArray(value)) {
    value.forEach((item) => rewritePredicate(item, transform));
    return;
  }
  if (typeof value.field === "string") {
    const replacement = { ...transform({ ...value }) };
    for (const key of Object.keys(value)) delete value[key];
    Object.assign(value, replacement);
    return;
  }
  for (const child of Object.values(value)) rewritePredicate(child, transform);
}

function rewriteMedicationListPredicates(tree) {
  for (const node of tree.nodes || []) {
    if (!node.logic?.predicate) continue;
    rewritePredicate(node.logic.predicate, (leaf) => {
      if (leaf.field === "medication.previousEncounterAgentCount") {
        const op = leaf.op === "in" ? "lengthIn" : leaf.op === "eq" ? "lengthEq" : leaf.op === "gte" ? "lengthGte" : leaf.op;
        return { ...leaf, field: "medication.previousEncounterDrugClassList", op };
      }
      if (leaf.field === "medication.currentDrugClassCount") {
        const op = leaf.op === "eq" ? "lengthEq" : leaf.op === "gte" ? "lengthGte" : leaf.op;
        return { ...leaf, field: "medication.currentDrugClassList", op };
      }
      if (leaf.field === "medication.currentIncludesDiuretic" && leaf.op === "eq" && leaf.value === true) {
        return { field: "medication.currentDrugClassList", op: "contains", value: "diuretic" };
      }
      return leaf;
    });
  }
}

function setVariableDataType(variables, variableId, dataType) {
  const variable = variables.find((item) => item.id === variableId);
  if (variable) variable.dataType = dataType;
}

function simplifyHighNormalPredicate(node) {
  if (!node?.logic) return;
  node.logic.predicate = {
    any: [
      {
        all: [
          { field: "bp.office3.systolicMmHg", op: "gte", value: 130 },
          { field: "bp.office3.systolicMmHg", op: "lte", value: 139 },
        ],
      },
      {
        all: [
          { field: "bp.office3.diastolicMmHg", op: "gte", value: 85 },
          { field: "bp.office3.diastolicMmHg", op: "lte", value: 89 },
        ],
      },
    ],
  };
  node.display = {
    ...node.display,
    title: "HATT 130–139 mmHg hoặc HATTr 85–89 mmHg?",
    detail: "Đúng khi HATT nằm trong 130–139 mmHg hoặc HATTr nằm trong 85–89 mmHg.",
  };
}

const RISK_SOURCE = {
  sourceId: "image_04_risk_stratification",
  page: 1,
  section: "Bảng phân tầng nguy cơ trong tăng huyết áp",
  tableOrFigure: "04_hypertension_risk_stratification.png",
};

function riskSource(note) {
  return { ...RISK_SOURCE, note };
}

function riskCondition(id, title, detail, predicate) {
  return {
    id,
    type: "condition",
    display: { title, detail },
    sourceRefs: [riskSource(title)],
    logic: { predicate },
  };
}

function riskInference(id, title, resultCode, severity) {
  return {
    id,
    type: "inference",
    display: { title },
    sourceRefs: [riskSource(title)],
    data: {
      resultCode,
      severity,
      sets: { "risk.class": resultCode.replace("risk_", "") },
      outcomeCode: resultCode,
    },
  };
}

function riskLink(id, riskClass) {
  return {
    id,
    type: "link",
    display: {
      title: "Chuyển sang Cây 2: Ngưỡng và đích điều trị",
      detail: `Tiếp tục với kết quả phân tầng nguy cơ ${riskClass}.`,
    },
    sourceRefs: [riskSource("Liên kết kết quả phân tầng sang Cây 2")],
    data: {
      targetTreeId: "bp_thresholds_targets",
      callMode: "navigate_only",
      passContext: true,
      returnPolicy: "merge_context",
      sets: {},
    },
  };
}

function diagnosisRiskLink(id, sourceRefs) {
  return {
    id,
    type: "link",
    display: {
      title: "Chuyển sang Cây 4: Phân tầng nguy cơ",
      detail: "Dùng kết quả chẩn đoán và hồ sơ nguy cơ của người bệnh.",
    },
    sourceRefs: sourceRefs || [],
    data: {
      targetTreeId: "hypertension_risk_stratification",
      callMode: "navigate_only",
      passContext: true,
      returnPolicy: "merge_context",
      sets: {},
    },
  };
}

function rewriteRiskTree(tree) {
  const highRiskCondition = {
    any: [
      { field: "comorbidity.leftVentricularHypertrophy", op: "eq", value: true },
      { field: "risk.ckdStageAtLeast3", op: "eq", value: true },
      { field: "comorbidity.diabetes", op: "eq", value: true },
      { field: "risk.cardiovascularDisease", op: "eq", value: true },
    ],
  };
  const grade2Condition = {
    any: [
      { field: "bp.latest.systolicMmHg", op: "gte", value: 160 },
      { field: "bp.latest.diastolicMmHg", op: "gte", value: 100 },
    ],
  };
  const veryHighGrade2Condition = {
    any: [
      { field: "bp.latest.systolicMmHg", op: "gte", value: 180 },
      { field: "bp.latest.diastolicMmHg", op: "gte", value: 110 },
    ],
  };
  const grade1Condition = {
    any: [
      {
        all: [
          { field: "bp.latest.systolicMmHg", op: "gte", value: 140 },
          { field: "bp.latest.systolicMmHg", op: "lte", value: 159 },
        ],
      },
      {
        all: [
          { field: "bp.latest.diastolicMmHg", op: "gte", value: 90 },
          { field: "bp.latest.diastolicMmHg", op: "lte", value: 99 },
        ],
      },
    ],
  };
  const highNormalCondition = {
    any: [
      {
        all: [
          { field: "bp.latest.systolicMmHg", op: "gte", value: 130 },
          { field: "bp.latest.systolicMmHg", op: "lte", value: 139 },
        ],
      },
      {
        all: [
          { field: "bp.latest.diastolicMmHg", op: "gte", value: 85 },
          { field: "bp.latest.diastolicMmHg", op: "lte", value: 89 },
        ],
      },
    ],
  };
  const normalCondition = {
    all: [
      { field: "bp.latest.systolicMmHg", op: "lt", value: 130 },
      { field: "bp.latest.diastolicMmHg", op: "lt", value: 85 },
    ],
  };
  const factorAtLeastOne = { field: "risk.factorCount", op: "gte", value: 1 };
  const factorAtLeastThree = { field: "risk.factorCount", op: "gte", value: 3 };

  tree.name = "Cây phân tầng nguy cơ tăng huyết áp";
  tree.purpose = "Phân tầng nguy cơ thấp, trung bình hoặc cao theo bảng nguy cơ: bệnh đồng mắc/tổn thương cơ quan đích, mức huyết áp gần nhất và số yếu tố nguy cơ.";
  tree.inputVariables = [
    "bp.latest.systolicMmHg",
    "bp.latest.diastolicMmHg",
    "risk.factorCount",
    "comorbidity.leftVentricularHypertrophy",
    "risk.ckdStageAtLeast3",
    "comorbidity.diabetes",
    "risk.cardiovascularDisease",
  ];
  tree.outputVariables = ["risk.class"];
  tree.linksTo = ["bp_thresholds_targets"];
  tree.nodes = [
    {
      id: "risk_start",
      type: "start",
      display: {
        title: "Thông tin huyết áp và yếu tố nguy cơ",
        detail: "Đánh giá theo bảng phân tầng nguy cơ tăng huyết áp.",
      },
      sourceRefs: [riskSource("Bắt đầu phân tầng nguy cơ")],
    },
    riskCondition(
      "risk_mandatory_high",
      "Có tổn thương cơ quan đích, CKD giai đoạn ≥3, đái tháo đường hoặc bệnh tim mạch?",
      "Chỉ cần có ít nhất một trong bốn nhóm bệnh/tình trạng này là nguy cơ cao.",
      highRiskCondition,
    ),
    riskInference("risk_infer_high_mandatory", "Nguy cơ cao", "risk_high", "high"),
    riskLink("risk_link_high_mandatory", "cao"),
    riskCondition(
      "risk_grade2",
      "HATT ≥160 mmHg hoặc HATTr ≥100 mmHg?",
      "Nhóm huyết áp độ 2 theo bảng phân tầng.",
      grade2Condition,
    ),
    riskCondition(
      "risk_grade2_very_high",
      "HATT ≥180 mmHg hoặc HATTr ≥110 mmHg?",
      "Mức huyết áp rất cao trong nhóm độ 2 được xếp nguy cơ cao.",
      veryHighGrade2Condition,
    ),
    riskCondition(
      "risk_grade2_factor",
      "Có ít nhất 1 yếu tố nguy cơ?",
      "Đếm từ biến số yếu tố nguy cơ chuẩn của bệnh nhân.",
      factorAtLeastOne,
    ),
    riskInference("risk_infer_high_grade2_very_high", "Nguy cơ cao", "risk_high", "high"),
    riskLink("risk_link_high_grade2_very_high", "cao"),
    riskInference("risk_infer_high_grade2_factor", "Nguy cơ cao", "risk_high", "high"),
    riskLink("risk_link_high_grade2_factor", "cao"),
    riskInference("risk_infer_medium_grade2", "Nguy cơ trung bình", "risk_medium", "medium"),
    riskLink("risk_link_medium_grade2", "trung bình"),
    riskCondition(
      "risk_grade1",
      "HATT 140–159 mmHg hoặc HATTr 90–99 mmHg?",
      "Nhóm huyết áp độ 1 theo bảng phân tầng.",
      grade1Condition,
    ),
    riskCondition(
      "risk_grade1_three",
      "Có ≥3 yếu tố nguy cơ?",
      "Từ 3 yếu tố nguy cơ trở lên được xếp nguy cơ cao ở nhóm huyết áp độ 1.",
      factorAtLeastThree,
    ),
    riskCondition(
      "risk_grade1_one",
      "Có 1 hoặc 2 yếu tố nguy cơ?",
      "Nhánh này được chọn khi chưa đạt ngưỡng ≥3 yếu tố nguy cơ và có ít nhất 1 yếu tố.",
      factorAtLeastOne,
    ),
    riskInference("risk_infer_high_grade1", "Nguy cơ cao", "risk_high", "high"),
    riskLink("risk_link_high_grade1", "cao"),
    riskInference("risk_infer_medium_grade1", "Nguy cơ trung bình", "risk_medium", "medium"),
    riskLink("risk_link_medium_grade1", "trung bình"),
    riskInference("risk_infer_low_grade1", "Nguy cơ thấp", "risk_low", "low"),
    riskLink("risk_link_low_grade1", "thấp"),
    riskCondition(
      "risk_high_normal",
      "HATT 130–139 mmHg hoặc HATTr 85–89 mmHg?",
      "Nhóm huyết áp bình thường cao theo bảng phân tầng.",
      highNormalCondition,
    ),
    riskInference("risk_infer_low_high_normal", "Nguy cơ thấp", "risk_low", "low"),
    riskLink("risk_link_low_high_normal", "thấp"),
    riskCondition(
      "risk_normal",
      "HATT <130 mmHg và HATTr <85 mmHg?",
      "Huyết áp bình thường được xếp nguy cơ thấp trong flow này.",
      normalCondition,
    ),
    riskInference("risk_infer_low_normal", "Nguy cơ thấp", "risk_low", "low"),
    riskLink("risk_link_low_normal", "thấp"),
    {
      id: "risk_end_review",
      type: "end",
      display: { title: "Cần rà soát dữ liệu huyết áp" },
      sourceRefs: [riskSource("Dữ liệu không thuộc các khoảng huyết áp hợp lệ")],
      data: { resultCode: "risk_review_required", outcomeCode: "risk_review_required" },
    },
  ];
  tree.edges = [
    { from: "risk_start", to: "risk_mandatory_high", when: "default" },
    { from: "risk_mandatory_high", to: "risk_infer_high_mandatory", when: "true", label: "TOD/CKD giai đoạn ≥3/ĐTĐ/bệnh tim mạch" },
    { from: "risk_infer_high_mandatory", to: "risk_link_high_mandatory", when: "default" },
    { from: "risk_mandatory_high", to: "risk_grade2", when: "false", label: "Không có TOD/CKD giai đoạn ≥3/ĐTĐ/bệnh tim mạch" },
    { from: "risk_grade2", to: "risk_grade2_very_high", when: "true", label: "HATT ≥160 hoặc HATTr ≥100" },
    { from: "risk_grade2", to: "risk_grade1", when: "false", label: "HATT <160 và HATTr <100" },
    { from: "risk_grade2_very_high", to: "risk_infer_high_grade2_very_high", when: "true", label: "HATT ≥180 hoặc HATTr ≥110" },
    { from: "risk_infer_high_grade2_very_high", to: "risk_link_high_grade2_very_high", when: "default" },
    { from: "risk_grade2_very_high", to: "risk_grade2_factor", when: "false", label: "HATT <180 và HATTr <110" },
    { from: "risk_grade2_factor", to: "risk_infer_high_grade2_factor", when: "true", label: "≥1 yếu tố nguy cơ" },
    { from: "risk_infer_high_grade2_factor", to: "risk_link_high_grade2_factor", when: "default" },
    { from: "risk_grade2_factor", to: "risk_infer_medium_grade2", when: "false", label: "0 yếu tố nguy cơ" },
    { from: "risk_infer_medium_grade2", to: "risk_link_medium_grade2", when: "default" },
    { from: "risk_grade1", to: "risk_grade1_three", when: "true", label: "HATT 140–159 hoặc HATTr 90–99" },
    { from: "risk_grade1", to: "risk_high_normal", when: "false", label: "Không thuộc HATT 140–159 hoặc HATTr 90–99" },
    { from: "risk_grade1_three", to: "risk_infer_high_grade1", when: "true", label: "≥3 yếu tố nguy cơ" },
    { from: "risk_infer_high_grade1", to: "risk_link_high_grade1", when: "default" },
    { from: "risk_grade1_three", to: "risk_grade1_one", when: "false", label: "<3 yếu tố nguy cơ" },
    { from: "risk_grade1_one", to: "risk_infer_medium_grade1", when: "true", label: "1–2 yếu tố nguy cơ" },
    { from: "risk_infer_medium_grade1", to: "risk_link_medium_grade1", when: "default" },
    { from: "risk_grade1_one", to: "risk_infer_low_grade1", when: "false", label: "0 yếu tố nguy cơ" },
    { from: "risk_infer_low_grade1", to: "risk_link_low_grade1", when: "default" },
    { from: "risk_high_normal", to: "risk_infer_low_high_normal", when: "true", label: "HATT 130–139 hoặc HATTr 85–89" },
    { from: "risk_infer_low_high_normal", to: "risk_link_low_high_normal", when: "default" },
    { from: "risk_high_normal", to: "risk_normal", when: "false", label: "Không thuộc HATT 130–139 hoặc HATTr 85–89" },
    { from: "risk_normal", to: "risk_infer_low_normal", when: "true", label: "HATT <130 và HATTr <85" },
    { from: "risk_infer_low_normal", to: "risk_link_low_normal", when: "default" },
    { from: "risk_normal", to: "risk_end_review", when: "false", label: "Không thuộc khoảng huyết áp hợp lệ" },
  ];
  tree.sourceRefs = [riskSource("Cây được xây theo Bảng 2 phân tầng nguy cơ")];
  tree.notes = [
    "Cây chỉ dùng các biến chuẩn: HATT/HATTr gần nhất, số yếu tố nguy cơ, dày thất trái, CKD giai đoạn ≥3, đái tháo đường và bệnh tim mạch.",
    "Bệnh đồng mắc/tổn thương cơ quan đích hoặc bệnh tim mạch: nguy cơ cao ở mọi mức huyết áp trong bảng.",
    "Độ 2: HATT ≥180 hoặc HATTr ≥110 là nguy cơ cao; mức còn lại của độ 2 có 0 YTNC là trung bình và có ≥1 YTNC là cao.",
    "Độ 1: 0 YTNC thấp; 1–2 YTNC trung bình; ≥3 YTNC cao.",
    "Bình thường cao: nguy cơ thấp theo bảng phân tầng, không phân tiếp theo số YTNC.",
    "Mỗi kết quả phân tầng được liên kết sang Cây 2 để xác định ngưỡng và đích điều trị.",
  ];
}

const bundle = readJson(bundlePath);
const regimenSource = {
  id: "medication.regimenStartDate",
  label: "Ngày bắt đầu hoặc chỉnh phác đồ",
  dataType: "string",
  unit: null,
  requiredForEvaluation: false,
  definition: "Ngày bắt đầu hoặc ngày thay đổi gần nhất của phác đồ đang đánh giá; lấy từ lịch sử kê đơn/MedicationRequest của hồ sơ bệnh nhân.",
  sourceSystem: "medication",
  sourceRefs: [{
    sourceId: "image_05_uncontrolled_resistant",
    page: 1,
    section: "Phân loại tăng huyết áp không kiểm soát/kháng trị",
    tableOrFigure: "05_uncontrolled_resistant_hypertension.png",
    note: "Ngày nguồn để tính số tuần phác đồ ổn định; không phải biến kết quả nhập tay.",
  }],
  validation: { maxLength: 10 },
};
const regimenDerived = {
  id: "medication.regimenStableWeeks",
  label: "Số tuần phác đồ ổn định",
  dataType: "number",
  unit: "week",
  requiredForEvaluation: false,
  definition: "Tự tính bằng số tuần tròn từ medication.regimenStartDate đến ngày khám (asOf); không cho nhập trực tiếp.",
  sourceSystem: "derived",
  sourceRefs: regimenSource.sourceRefs,
  derivedFrom: ["medication.regimenStartDate"],
  validation: { minimum: 0, maximum: 104 },
};
ensureVariable(bundle, regimenSource);
ensureVariable(bundle, regimenDerived);
const removeVariableIds = new Set([
  "treatment.targetProfile",
  "treatment.controlWindowMonths",
  "treatment.hasHighRiskComorbidity",
  "medication.currentHasUnmappedDrug",
  "medication.currentUnmappedDrugNames",
  "medication.previousEncounterUnmappedDrugNames",
  "medication.previousEncounterHasUnmappedDrug",
  "medication.previousEncounterAgentCount",
  "medication.previousEncounterDrugClassCodes",
  "medication.previousEncounterIncludesDiuretic",
  "medication.currentDrugClassCodes",
  "medication.currentDrugClassCount",
  "medication.currentIncludesDiuretic",
  "bp.officeAverageSystolicMmHg",
  "bp.officeReadingCount",
]);

bundle.variables = bundle.variables.filter((variable) => !removeVariableIds.has(variable.id));
removeKeys(bundle, removeVariableIds);
setVariableDataType(bundle.variables, "medication.currentDrugNames", "array");
setVariableDataType(bundle.variables, "medication.previousEncounterDrugNames", "array");

const diagnosis = bundle.trees.find((tree) => tree.id === "bp_diagnosis");
if (diagnosis) {
  const firstScreen = nodeById(diagnosis, "bp_first_screen");
  if (firstScreen) firstScreen.logic = { predicate: { any: [
    { field: "bp.office1.systolicMmHg", op: "gte", value: 180 },
    { field: "bp.office1.diastolicMmHg", op: "gte", value: 120 },
    { field: "comorbidity.targetOrganDamageOrCvd", op: "eq", value: true },
  ] } };
  const secondScreen = nodeById(diagnosis, "bp_second_screen");
  if (secondScreen) secondScreen.logic = { predicate: { any: [
    { all: [
      { field: "bp.office2.systolicMmHg", op: "gte", value: 140 },
      { field: "bp.office2.systolicMmHg", op: "lte", value: 179 },
    ] },
    { all: [
      { field: "bp.office2.diastolicMmHg", op: "gte", value: 90 },
      { field: "bp.office2.diastolicMmHg", op: "lte", value: 119 },
    ] },
    { field: "comorbidity.targetOrganDamageOrCvd", op: "eq", value: true },
  ] } };
  simplifyHighNormalPredicate(nodeById(diagnosis, "bp_third_high_normal_screen"));
  diagnosis.inputVariables = diagnosis.inputVariables.filter((id) => id !== "risk.cardiovascularDisease");
  diagnosis.inputVariables = [...new Set([...diagnosis.inputVariables, "comorbidity.targetOrganDamageOrCvd"])];
  setLabel(diagnosis, "bp_first_screen", "bp_crisis_result", "HATT ≥180 hoặc HATTr ≥120 hoặc TOD/CVD");
  setLabel(diagnosis, "bp_first_screen", "bp_second_screen", "Không đạt điều kiện cấp cứu");
  setLabel(diagnosis, "bp_second_screen", "bp_second_htn_result", "HATT 140–179 hoặc HATTr 90–119 hoặc TOD/CVD");
  setLabel(diagnosis, "bp_second_screen", "bp_third_normal_screen", "Không đạt điều kiện tăng huyết áp");
  setLabel(diagnosis, "bp_third_normal_screen", "bp_normal_result", "HATT <130 và HATTr <85");
  setLabel(diagnosis, "bp_third_normal_screen", "bp_third_high_normal_screen", "HATT ≥130 hoặc HATTr ≥85");
  setLabel(diagnosis, "bp_third_high_normal_screen", "bp_high_normal_result", "130≤HATT≤139 hoặc 85≤HATTr≤89");
  setLabel(diagnosis, "bp_third_high_normal_screen", "bp_third_htn_result", "HATT ≥140 hoặc HATTr ≥90");
  const diagnosisLinkTargets = [
    ["bp_infer_normal", "bp_link_risk_normal"],
    ["bp_infer_high_normal", "bp_link_risk_high_normal"],
    ["bp_infer_office3_htn", "bp_link_risk_office3_hypertension"],
    ["bp_infer_hypertension", "bp_link_risk_hypertension"],
  ];
  for (const [nodeId, linkId] of diagnosisLinkTargets) {
    const terminal = nodeById(diagnosis, nodeId);
    if (!terminal) continue;
    if (terminal.type === "end") terminal.type = "inference";
    terminal.data = { ...terminal.data, sets: { ...(terminal.data?.sets || {}) } };
    if (!diagnosis.nodes.some((node) => node.id === linkId)) {
      diagnosis.nodes.push(diagnosisRiskLink(linkId, terminal.sourceRefs));
    }
    if (!diagnosis.edges.some((item) => item.from === nodeId && item.to === linkId)) {
      diagnosis.edges.push({ from: nodeId, to: linkId, when: "default", label: "Đã phân loại huyết áp" });
    }
  }
  diagnosis.linksTo = ["hypertension_risk_stratification"];
}

const targets = bundle.trees.find((tree) => tree.id === "bp_thresholds_targets");
if (targets) {
  const removed = new Set([
    "threshold_hypertension",
    "threshold_high_normal_target",
    "threshold_link_treatment_high_normal_target",
    "threshold_high_risk",
    "threshold_high_risk_target",
    "threshold_link_treatment_high_risk",
    "threshold_review",
  ]);
  targets.nodes = targets.nodes.filter((node) => !removed.has(node.id));
  targets.edges = targets.edges.filter((item) => !removed.has(item.from) && !removed.has(item.to));

  replaceEdge(targets, "threshold_high_normal", ["threshold_hypertension", "threshold_hypertension_encounter"], {
    from: "threshold_high_normal",
    to: "threshold_hypertension_encounter",
    when: "false",
    label: "Huyết áp không thuộc nhóm bình thường-cao",
  });
  replaceEdge(targets, "threshold_high_normal_encounter", ["threshold_high_normal_target", "threshold_comorbidity"], {
    from: "threshold_high_normal_encounter",
    to: "threshold_comorbidity",
    when: "false",
    label: "Lần khám >1",
  });
  replaceEdge(targets, "threshold_hypertension_encounter", ["threshold_high_risk", "threshold_comorbidity"], {
    from: "threshold_hypertension_encounter",
    to: "threshold_comorbidity",
    when: "false",
    label: "Lần khám >1",
  });

  targets.inputVariables = [
    "bp.category",
    "encounter.number",
    "comorbidity.targetOrganDamageOrCvd",
  ];
  replaceField(targets, "treatment.hasHighRiskComorbidity", "comorbidity.targetOrganDamageOrCvd");
  setLabel(targets, "threshold_high_normal", "threshold_high_normal_encounter", "Huyết áp bình thường-cao");
  setLabel(targets, "threshold_high_normal_encounter", "threshold_high_normal_lifestyle", "Lần khám =1");
  setLabel(targets, "threshold_high_normal_encounter", "threshold_comorbidity", "Lần khám >1");
  setLabel(targets, "threshold_hypertension_encounter", "threshold_hypertension_lifestyle", "Lần khám =1");
  setLabel(targets, "threshold_hypertension_encounter", "threshold_comorbidity", "Lần khám >1");
  setLabel(targets, "threshold_comorbidity", "threshold_comorbidity_target", "Có bệnh đồng mắc/TOD/CVD");
  setLabel(targets, "threshold_comorbidity", "threshold_standard_target", "Không có bệnh đồng mắc/TOD/CVD");
  for (const node of targets.nodes) {
    if (node.sets) removeKeys(node.sets, removeVariableIds);
  }
}

const treatment = bundle.trees.find((tree) => tree.id === "optimized_hypertension_treatment");
if (treatment) {
  delete treatment.entryPreconditions;
  const removed = new Set(["optimized_previous_drug_mapping"]);
  treatment.nodes = treatment.nodes.filter((node) => !removed.has(node.id));
  treatment.edges = treatment.edges.filter((item) => !removed.has(item.from) && !removed.has(item.to));
  const treatmentNodeIds = new Set(treatment.nodes.map((node) => node.id));
  treatment.edges = treatment.edges.filter((item) => treatmentNodeIds.has(item.from) && treatmentNodeIds.has(item.to));
  replaceField(treatment, "treatment.hasHighRiskComorbidity", "comorbidity.targetOrganDamageOrCvd");
  treatment.inputVariables = treatment.inputVariables.filter((id) => id !== "treatment.hasHighRiskComorbidity");
  treatment.inputVariables = [...new Set([...treatment.inputVariables, "comorbidity.targetOrganDamageOrCvd"])];
  rewriteMedicationListPredicates(treatment);
  treatment.inputVariables = [...new Set([
    ...treatment.inputVariables.filter((id) => !removeVariableIds.has(id)),
    "medication.previousEncounterDrugNames",
    "medication.previousEncounterDrugClassList",
  ])];
  const labels = new Map([
    ["optimized_encounter_type|optimized_followup_mandatory", "Lần khám >1"],
    ["optimized_encounter_type|optimized_new_mandatory", "Lần khám =1"],
    ["optimized_new_mandatory|optimized_mandatory_branch", "Có chỉ định bắt buộc"],
    ["optimized_new_mandatory|optimized_new_recommendation", "Không có chỉ định bắt buộc"],
    ["optimized_followup_count_valid|optimized_previous_count_one", "Số nhóm thuốc 1–4"],
    ["optimized_followup_count_valid|optimized_end_review", "Số nhóm thuốc ngoài 1–4"],
    ["optimized_previous_count_one|optimized_previous_count_two", "Số nhóm thuốc 2–4"],
    ["optimized_previous_count_two|optimized_previous_count_three", "Số nhóm thuốc 3–4"],
    ["optimized_previous_count_three|optimized_previous_count_four", "Số nhóm thuốc =4"],
    ["optimized_previous_count_four|optimized_end_review", "Số nhóm thuốc ngoài 1–4"],
    ["optimized_control_after_two|optimized_infer_two_controlled", "HA đạt đích điều trị"],
    ["optimized_control_after_two|optimized_infer_escalate_three", "HA chưa đạt đích điều trị"],
    ["optimized_control_after_three|optimized_infer_three_controlled", "HA đạt đích điều trị"],
    ["optimized_control_after_three|optimized_infer_escalate_four", "HA chưa đạt đích điều trị"],
    ["optimized_control_after_four|optimized_infer_four_controlled", "HA đạt đích điều trị"],
    ["optimized_control_after_four|optimized_infer_resistant", "HA chưa đạt đích điều trị"],
    ["optimized_followup_mandatory|optimized_mandatory_branch", "Có chỉ định bắt buộc"],
    ["optimized_new_recommendation|optimized_end_new_lifestyle", "Cần thay đổi lối sống trước"],
    ["optimized_new_recommendation|optimized_initial_risk", "Cần điều trị thuốc"],
    ["optimized_initial_risk|optimized_end_initial_combination", "Đủ điều kiện phối hợp ban đầu"],
    ["optimized_initial_risk|optimized_infer_new", "Chưa đủ điều kiện phối hợp ban đầu"],
  ]);
  for (const item of treatment.edges) {
    const label = labels.get(`${item.from}|${item.to}`);
    if (label) item.label = label;
  }
}

const resistant = bundle.trees.find((tree) => tree.id === "uncontrolled_resistant_hypertension");
if (resistant) {
  const removed = new Set(["resistant_drug_mapping", "resistant_end_unknown_drug"]);
  const unmappedDrugNodes = new Set(
    resistant.nodes
      .filter((node) => node.logic?.predicate?.field === "medication.currentHasUnmappedDrug")
      .map((node) => node.id),
  );
  for (const nodeId of unmappedDrugNodes) removed.add(nodeId);
  resistant.nodes = resistant.nodes.filter((node) => !removed.has(node.id));
  resistant.edges = resistant.edges.filter((item) => !removed.has(item.from) && !removed.has(item.to));
  if (!resistant.nodes.some((node) => node.id === "resistant_stable")) {
    const sourceRef = {
      sourceId: "image_05_uncontrolled_resistant",
      page: 1,
      section: "Phân loại tăng huyết áp không kiểm soát/kháng trị",
      tableOrFigure: "05_uncontrolled_resistant_hypertension.png",
      note: "Phác đồ ổn định ít nhất 4 tuần trước khi phân loại.",
    };
    resistant.nodes.push({
      id: "resistant_stable",
      type: "condition",
      display: {
        title: "Phác đồ đã ổn định ≥4 tuần?",
        detail: "Tự tính từ ngày bắt đầu/chỉnh phác đồ và ngày khám; không nhập số tuần.",
      },
      sourceRefs: [sourceRef],
      logic: { predicate: { field: "medication.regimenStableWeeks", op: "gte", value: 4 } },
    });
  }
  if (!resistant.nodes.some((node) => node.id === "resistant_end_defer")) {
    const sourceRef = {
      sourceId: "image_05_uncontrolled_resistant",
      page: 1,
      section: "Phân loại tăng huyết áp không kiểm soát/kháng trị",
      tableOrFigure: "05_uncontrolled_resistant_hypertension.png",
      note: "Chưa đủ thời gian ổn định phác đồ để phân loại.",
    };
    resistant.nodes.push({
      id: "resistant_end_defer",
      type: "end",
      display: {
        title: "Đánh giá lại sau",
        detail: "Phác đồ chưa ổn định đủ 4 tuần.",
      },
      sourceRefs: [sourceRef],
      data: {
        resultCode: "resistant_defer",
        outcomeCode: "resistant_defer_reassess",
      },
    });
  }
  resistant.inputVariables = [...new Set([
    ...resistant.inputVariables.filter((id) => !removeVariableIds.has(id)),
    "bp.latest.systolicMmHg",
    "medication.currentDrugNames",
    "medication.currentDrugClassList",
    "medication.regimenStableWeeks",
  ])].filter((id) => !["bp.officeAverageSystolicMmHg", "bp.officeReadingCount"].includes(id));
  rewriteMedicationListPredicates(resistant);
  replaceEdge(resistant, "resistant_range", ["resistant_stable", "resistant_agent_count"], {
    from: "resistant_range",
    to: "resistant_stable",
    when: "true",
    label: "HATT lần gần nhất 140–169 mmHg",
  });
  replaceEdge(resistant, "resistant_stable", ["resistant_agent_count", "resistant_end_defer"], {
    from: "resistant_stable",
    to: "resistant_agent_count",
    when: "true",
    label: "Phác đồ ổn định ≥4 tuần",
  });
  if (!resistant.edges.some((item) => item.from === "resistant_stable" && item.to === "resistant_end_defer")) {
    resistant.edges.push({
      from: "resistant_stable",
      to: "resistant_end_defer",
      when: "false",
      label: "Phác đồ ổn định <4 tuần",
    });
  }
  replaceEdge(resistant, "resistant_range", ["resistant_end_out_of_range"], {
    from: "resistant_range",
    to: "resistant_end_out_of_range",
    when: "false",
    label: "HATT ngoài khoảng 140–169 mmHg",
  });
  resistant.edges = resistant.edges.filter(
    (item, index, all) => all.findIndex((candidate) => candidate.from === item.from && candidate.to === item.to && candidate.when === item.when) === index,
  );
  setLabel(resistant, "resistant_range", "resistant_agent_count", "HATT lần gần nhất 140–169 mmHg");
  setLabel(resistant, "resistant_range", "resistant_end_out_of_range", "HATT ngoài khoảng 140–169 mmHg");
  setLabel(resistant, "resistant_stable", "resistant_agent_count", "Phác đồ ổn định ≥4 tuần");
  setLabel(resistant, "resistant_stable", "resistant_end_defer", "Phác đồ ổn định <4 tuần");
  setLabel(resistant, "resistant_agent_count", "resistant_infer_uncontrolled", "Đúng 2 nhóm thuốc");
  setLabel(resistant, "resistant_agent_count", "resistant_agent_count_ge3", "Số nhóm thuốc khác 2");
  setLabel(resistant, "resistant_agent_count_ge3", "resistant_diuretic", "Từ 3 nhóm thuốc");
  setLabel(resistant, "resistant_agent_count_ge3", "resistant_end_agent_count_review", "Số nhóm thuốc <3");
  setLabel(resistant, "resistant_diuretic", "resistant_infer_resistant", "Có thuốc lợi tiểu");
  setLabel(resistant, "resistant_diuretic", "resistant_end_add_diuretic", "Không có thuốc lợi tiểu");
  for (const node of resistant.nodes) {
    if (node.id === "resistant_range" && Array.isArray(node.logic?.predicate?.all)) {
      node.logic.predicate = {
        all: [
          { field: "bp.latest.systolicMmHg", op: "gte", value: 140 },
          { field: "bp.latest.systolicMmHg", op: "lte", value: 169 },
        ],
      };
      node.display = {
        ...node.display,
        title: "HATT lần đo gần nhất 140–169 mmHg?",
        detail: "HATT lần đo gần nhất được tự động lấy từ lần 3, nếu thiếu thì lần 2 hoặc lần 1.",
      };
    }
    if (node.id === "resistant_stable") {
      node.display = {
        ...node.display,
        title: "Phác đồ đã ổn định ≥4 tuần?",
        detail: "Tự tính từ ngày bắt đầu/chỉnh phác đồ và ngày khám; không nhập số tuần.",
      };
    }
  }
}

const riskTree = bundle.trees.find((tree) => tree.id === "hypertension_risk_stratification");
if (riskTree) {
  rewriteRiskTree(riskTree);
  const labels = new Map([
    ["risk_high_comorbidity|risk_infer_high_comorbidity", "Có TOD/CKD giai đoạn ≥3/ĐTĐ/bệnh tim mạch"],
    ["risk_high_comorbidity|risk_grade2", "Không có TOD/CKD giai đoạn ≥3/ĐTĐ/bệnh tim mạch"],
    ["risk_grade2|risk_grade2_high_band", "HATT ≥160 hoặc HATTr ≥100 mmHg"],
    ["risk_grade2|risk_grade1", "HATT <160 và HATTr <100 mmHg"],
    ["risk_grade2_high_band|risk_infer_high_grade2", "HATT ≥180 hoặc HATTr ≥110 mmHg"],
    ["risk_grade2_high_band|risk_grade2_factors", "HATT 160–179 và HATTr 100–109 mmHg"],
    ["risk_grade2_factors|risk_infer_high_grade2", "Có ≥1 yếu tố nguy cơ"],
    ["risk_grade2_factors|risk_infer_medium_grade2", "Không có yếu tố nguy cơ"],
    ["risk_grade1|risk_grade1_three", "HATT 140–159 hoặc HATTr 90–99 mmHg"],
    ["risk_grade1|risk_high_normal", "HATT <140 và HATTr <90 mmHg"],
    ["risk_grade1_three|risk_infer_high_grade1", "≥3 yếu tố nguy cơ"],
    ["risk_grade1_three|risk_grade1_one", "0–2 yếu tố nguy cơ"],
    ["risk_grade1_one|risk_infer_medium_grade1", "1–2 yếu tố nguy cơ"],
    ["risk_grade1_one|risk_infer_low_grade1", "0 yếu tố nguy cơ"],
    ["risk_high_normal|risk_high_normal_three", "HATT 130–139 hoặc HATTr 85–89 mmHg"],
    ["risk_high_normal|risk_normal", "HATT <130 và HATTr <85 mmHg"],
    ["risk_high_normal_three|risk_infer_medium_high_normal", "≥3 yếu tố nguy cơ"],
    ["risk_high_normal_three|risk_infer_low_high_normal", "0–2 yếu tố nguy cơ"],
    ["risk_normal|risk_infer_low_normal", "HATT <130 và HATTr <85 mmHg"],
    ["risk_normal|risk_end_review", "HATT ≥130 hoặc HATTr ≥85 mmHg"],
  ]);
  for (const item of riskTree.edges) {
    const label = labels.get(`${item.from}|${item.to}`);
    if (label) item.label = label;
  }
}

for (const tree of bundle.trees) {
  for (const item of tree.edges) {
    if (typeof item.when === "boolean") item.when = String(item.when);
  }
  normalizeOutputDisplays(tree);
}

writeJson(bundlePath, bundle);

const variables = readJson(variablesPath);
variables.variables = variables.variables.filter((variable) => !removeVariableIds.has(variable.id));
setVariableDataType(variables.variables, "medication.currentDrugNames", "array");
setVariableDataType(variables.variables, "medication.previousEncounterDrugNames", "array");
ensureVariable(variables, regimenSource);
ensureVariable(variables, regimenDerived);
if (variables.variablePresentation) {
  variables.variablePresentation["medication.regimenStartDate"] = {
    section: "treatment",
    control: "date",
    displayOrder: 40,
    placeholder: "Ngày bắt đầu/chỉnh phác đồ",
    helpText: "Dùng để tự tính số tuần phác đồ ổn định đến ngày khám.",
  };
}
const derivedFields = variables.inputForm?.derivedPresentation?.fields;
if (Array.isArray(derivedFields) && !derivedFields.includes("medication.regimenStableWeeks")) {
  derivedFields.push("medication.regimenStableWeeks");
}
if (Array.isArray(variables.automaticCodeDerivation?.rules)) {
  variables.automaticCodeDerivation.rules = variables.automaticCodeDerivation.rules.filter(
    (rule) => !removeVariableIds.has(rule.variableId),
  );
}
removeKeys(variables, removeVariableIds);
removeStringValues(variables, removeVariableIds);
writeJson(variablesPath, variables);

const triggers = readJson(triggersPath);
removeKeys(triggers, new Set(["treatment.targetProfile", "treatment.controlWindowMonths"]));
writeJson(triggersPath, triggers);

console.log("Applied review corrections to bundle, variables, and trigger registry.");
