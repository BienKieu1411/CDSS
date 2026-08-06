"use strict";

const state = {
  bundle: null,
  treeId: null,
  previewTimer: null,
  previewSequence: 0,
  treeJobs: Object.create(null),
  runtimeBundles: Object.create(null),
  editedTrees: Object.create(null),
  nodeWorkingTree: null,
  nodeId: null,
};
const $ = (id) => document.getElementById(id);
const pretty = (value) => JSON.stringify(value, null, 2);
const colors = { start: "#d7f7e8", condition: "#ffe5a6", inference: "#b9d6ff", link: "#f7bddb", end: "#dec5f6" };
const displayTranslations = new Map([
  ["BP Diagnosis Tree", "Cây chẩn đoán tăng huyết áp"],
  ["BP Thresholds and Targets Tree", "Ngưỡng và mục tiêu huyết áp"],
  ["Optimized Hypertension Treatment Tree", "Điều trị tăng huyết áp tối ưu"],
  ["Hypertension Risk Stratification Tree", "Phân tầng nguy cơ tăng huyết áp"],
  ["Hypertension General — Phân loại THA", "Phân loại tăng huyết áp tổng quát"],
  ["Seated SBP 140–169 mmHg?", "HATT tư thế ngồi 140–169 mmHg?"],
  ["Out of Range — Cần đánh giá thêm", "Ngoài khoảng — Cần đánh giá thêm"],
  ["Defer — Đánh giá lại sau", "Tạm hoãn — Đánh giá lại sau"],
  ["Uncontrolled HTN — Phác đồ 2 thuốc", "THA chưa kiểm soát — Phác đồ 2 thuốc"],
  ["Resistant HTN — ≥3 thuốc + lợi tiểu", "THA kháng trị — ≥3 thuốc + lợi tiểu"],
  ["Yes", "Có"],
  ["No", "Không"],
  ["Exactly 2", "Đúng 2"],
  ["Both arms", "Cả hai tay"],
  ["Target met", "Đạt mục tiêu"],
  ["Not met", "Chưa đạt mục tiêu"],
  [" (reading)", ""],
  [" (week)", ""],
  [" (class)", ""],
  ["clinical flow", "luồng lâm sàng"],
]);
function localizeText(value) {
  let text = String(value || "");
  displayTranslations.forEach((translated, source) => { text = text.split(source).join(translated); });
  return text;
}
let graphInstance = null;
let visualEndAliases = new Map();

async function api(url, options = {}) {
  const response = await fetch(url, { headers: { "Content-Type": "application/json" }, ...options });
  const data = await response.json();
  if (!response.ok) throw new Error((data.errors || ["Request failed"]).join("\n"));
  return data;
}

function tree() { return state.bundle.trees.find((item) => item.id === state.treeId); }
function activeTree() { return state.editedTrees[state.treeId] || tree(); }
function treeLabel(treeId) {
  const target = state.bundle?.trees?.find((item) => item.id === treeId);
  return localizeText(target?.name || "cây liên kết");
}
function variableLabel(variableId) {
  const variable = state.bundle.variables.find((item) => item.id === variableId);
  return localizeText(variable?.label || "Thông tin cần nhập");
}
function missingVariableLabels(variableIds) {
  return (variableIds || []).map(variableLabel);
}
function makeGeneratedTreeId(name) {
  const normalized = String(name || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
  return `uploaded_${normalized || "tree"}_${Date.now()}`;
}
function showStatus(message, kind = "") { $("ui-status").textContent = message; $("ui-status").className = `status ${kind}`; }
function showPipelineStatus(message, kind = "") { $("pipeline-status").textContent = message; $("pipeline-status").className = `status ${kind}`; }
function nodeData(node) {
  if (node && node.data && typeof node.data === "object") return node.data;
  if (typeof node?.dataJson === "string") {
    try { return JSON.parse(node.dataJson); } catch (error) { return {}; }
  }
  return {};
}
function linkTarget(node) { return nodeData(node).targetTreeId; }
const OPTIMIZED_TREE_ID = "optimized_hypertension_treatment";
const FLOW_DERIVED_VARIABLES = new Set([
  "treatment.recommendation",
  "treatment.targetSystolicMmHg",
  "treatment.targetDiastolicMmHg",
  "treatment.targetProfile",
  "treatment.controlWindowMonths",
]);
function inputVariableIdsForTree(current) {
  if (state.treeId !== OPTIMIZED_TREE_ID) return current.inputVariables || [];
  const flowTreeIds = ["bp_thresholds_targets", OPTIMIZED_TREE_ID, "uncontrolled_resistant_hypertension"];
  const ids = [];
  for (const treeId of flowTreeIds) {
    const source = treeId === state.treeId ? current : state.bundle.trees.find((item) => item.id === treeId);
    for (const variableId of source?.inputVariables || []) {
      if (!FLOW_DERIVED_VARIABLES.has(variableId) && !ids.includes(variableId)) ids.push(variableId);
    }
  }
  return ids;
}

function clearPathHighlight(message = "Nhập dữ liệu để xem đường đi trên cây.") {
  if (graphInstance) {
    graphInstance.nodes().removeClass("path-mode path-node path-current path-terminal");
    graphInstance.edges().removeClass("path-mode path-edge");
  }
  $("path-status").textContent = message;
  $("path-status").className = "path-status";
}

function highlightPath(result) {
  if (!graphInstance) return;
  const events = (result?.trace || []).filter((event) => event.treeId === state.treeId && event.nodeId);
  const nodeIds = events.map((event) => visualEndAliases.get(event.nodeId) || event.nodeId).filter((nodeId, index, ids) => index === 0 || nodeId !== ids[index - 1]);
  const nodeIdSet = new Set(nodeIds);
  const edgeKeys = new Set();
  for (let index = 1; index < nodeIds.length; index += 1) edgeKeys.add(`${nodeIds[index - 1]}->${nodeIds[index]}`);

  graphInstance.nodes().removeClass("path-mode path-node path-current path-terminal");
  graphInstance.edges().removeClass("path-mode path-edge");
  if (!events.length) {
    clearPathHighlight("Chưa có node nào được đánh giá.");
    return;
  }

  graphInstance.nodes().addClass("path-mode");
  graphInstance.edges().addClass("path-mode");
  graphInstance.nodes().forEach((node) => { if (nodeIdSet.has(node.id())) node.addClass("path-node"); });
  graphInstance.edges().forEach((edge) => {
    if (edgeKeys.has(`${edge.data("source")}->${edge.data("target")}`)) edge.addClass("path-edge");
  });

  const lastEvent = events[events.length - 1];
  const lastNode = graphInstance.getElementById(visualEndAliases.get(lastEvent.nodeId) || lastEvent.nodeId);
  if (result.status === "completed") lastNode.addClass("path-terminal");
  else lastNode.addClass("path-current");
  const terminal = result.status === "completed"
    ? `Kết quả: ${result.decision || result.resultCode || result.outcomeCode || "Hoàn tất"}`
    : result.status === "needs_data"
      ? `Đang chờ dữ liệu: ${missingVariableLabels(result.missingData).join(", ") || "chưa đủ điều kiện"}`
      : `Trạng thái: ${result.status}`;
  const linkNote = result.terminalTreeId && result.terminalTreeId !== state.treeId ? ` · chuyển đến ${treeLabel(result.terminalTreeId)}` : "";
  $("path-status").textContent = `Đường đi hiện tại: ${events.length} node${linkNote} · ${terminal}`;
  $("path-status").className = `path-status ${result.status === "completed" ? "completed" : "pending"}`;
}

function renderGraph(current) {
  const container = $("graph");
  if (graphInstance) graphInstance.destroy();
  const nodesById = Object.fromEntries(current.nodes.map((node) => [node.id, node]));
  const incomingByNode = Object.fromEntries(current.nodes.map((node) => [node.id, []]));
  current.edges.forEach((edge) => incomingByNode[edge.to]?.push(edge));
  visualEndAliases = new Map();
  current.nodes.forEach((node) => {
    if (node.type !== "end" || incomingByNode[node.id].length !== 1) return;
    const sourceId = incomingByNode[node.id][0].from;
    if (nodesById[sourceId]?.type === "inference") visualEndAliases.set(node.id, sourceId);
  });
  const visibleNodes = current.nodes.filter((node) => !visualEndAliases.has(node.id));
  const nodeData = visibleNodes.map((node) => {
    const title = localizeText(node.display?.title || "");
    return { data: { id: node.id, title, nodeType: node.type, label: title }, classes: node.type };
  });
  const edgeData = current.edges
    .filter((edge) => !visualEndAliases.has(edge.to))
    .map((edge, index) => ({ data: { id: `edge-${index}-${edge.from}-${edge.to}`, source: edge.from, target: edge.to, label: localizeText(edge.label || (edge.when === "default" ? "" : edge.when)) }, classes: current.nodes.find((node) => node.id === edge.from)?.type === "link" ? "link-edge" : "" }));

  graphInstance = cytoscape({
    container,
    elements: [...nodeData, ...edgeData],
    style: [
      { selector: "node", style: { "background-color": "data(nodeType)", "background-opacity": 1, "border-color": "#23466f", "border-width": 2, shape: "roundrectangle", width: 230, height: 112, label: "data(label)", color: "#14213b", "font-family": "Inter, ui-sans-serif, system-ui, sans-serif", "font-size": 12, "font-weight": 600, "text-wrap": "wrap", "text-max-width": 202, "text-valign": "center", "text-halign": "center", padding: 8, "overlay-opacity": 0, "shadow-blur": 8, "shadow-color": "#19345a", "shadow-opacity": 0.15, "shadow-offset-x": 0, "shadow-offset-y": 3 } },
      { selector: 'node[nodeType = "start"]', style: { "background-color": colors.start } },
      { selector: 'node[nodeType = "condition"]', style: { "background-color": colors.condition } },
      { selector: 'node[nodeType = "inference"]', style: { "background-color": colors.inference } },
      { selector: 'node[nodeType = "link"]', style: { "background-color": colors.link, "border-color": "#9d174d", cursor: "pointer" } },
      { selector: 'node[nodeType = "end"]', style: { "background-color": colors.end } },
      { selector: "node.path-mode", style: { opacity: 0.34 } },
      { selector: "node.path-node", style: { opacity: 1, "border-color": "#16a34a", "border-width": 4, "shadow-color": "#16a34a", "shadow-opacity": 0.4, "shadow-blur": 16 } },
      { selector: "node.path-current", style: { "background-color": "#fde68a", "border-color": "#d97706", "border-width": 5, "shadow-color": "#f59e0b", "shadow-opacity": 0.55, "shadow-blur": 18 } },
      { selector: "node.path-terminal", style: { "background-color": "#bfdbfe", "border-color": "#2563eb", "border-width": 5, "shadow-color": "#2563eb", "shadow-opacity": 0.55, "shadow-blur": 18 } },
      { selector: "edge", style: { width: 2, "line-color": "#6b7d97", "target-arrow-color": "#6b7d97", "target-arrow-shape": "triangle", "curve-style": "bezier", label: "data(label)", color: "#52637c", "font-size": 11, "font-weight": 600, "text-background-color": "#ffffff", "text-background-opacity": 0.9, "text-background-padding": 3, "text-rotation": "none", "text-margin-y": -4 } },
      { selector: ".link-edge", style: { "line-color": "#c0266e", "target-arrow-color": "#c0266e", "line-style": "dashed" } },
      { selector: "edge.path-mode", style: { opacity: 0.2 } },
      { selector: "edge.path-edge", style: { opacity: 1, width: 5, "line-color": "#16a34a", "target-arrow-color": "#16a34a", "z-index": 10 } },
      { selector: ":selected", style: { "border-color": "#2563eb", "border-width": 4, "shadow-opacity": 0.3 } },
    ],
    layout: { name: "dagre", rankDir: "TB", nodeSep: 70, edgeSep: 24, rankSep: 82, padding: 36, fit: true, animate: false },
    wheelSensitivity: 0.55,
    minZoom: 0.15,
    maxZoom: 2.2,
  });
  graphInstance.on("tap", "node", (event) => {
    const selected = current.nodes.find((node) => node.id === event.target.id());
    if (selected?.type !== "link") {
      openEditTree(selected?.id);
      return;
    }
    const targetTreeId = linkTarget(selected);
    if (targetTreeId && state.bundle.trees.some((item) => item.id === targetTreeId)) {
      selectTree(targetTreeId, `Đã chuyển đến cây liên kết: ${treeLabel(targetTreeId)}`);
    } else {
      showStatus("Không tìm thấy cây đích của liên kết.", "bad");
    }
  });
}

function renderInputForm(current) {
  const variables = Object.fromEntries(state.bundle.variables.map((item) => [item.id, item]));
  const form = $("input-form");
  form.innerHTML = "";
  inputVariableIdsForTree(current).forEach((id) => {
    const variable = variables[id];
    if (!variable) return;
    const card = document.createElement("div");
    card.className = "input-card";
    const label = document.createElement("label");
    label.htmlFor = `var-${id.replace(/[^A-Za-z0-9_-]/g, "_")}`;
    label.textContent = `${localizeText(variable.label || "Thông tin cần nhập")}${variable.unit ? ` (${localizeText(variable.unit)})` : ""}`;
    card.appendChild(label);
    let input;
    if (variable.dataType === "enum" || variable.dataType === "boolean") {
      input = document.createElement("select");
      input.add(new Option("Chưa nhập", ""));
      const values = variable.dataType === "boolean" ? ["true", "false"] : (variable.allowedValues || []);
      values.forEach((value) => input.add(new Option(value, value)));
    } else {
      input = document.createElement("input");
      input.type = variable.dataType === "string" ? "text" : "number";
      if (variable.dataType === "number") input.step = "any";
      if (variable.validation?.minimum != null) input.min = variable.validation.minimum;
      if (variable.validation?.maximum != null) input.max = variable.validation.maximum;
    }
    input.id = `var-${id.replace(/[^A-Za-z0-9_-]/g, "_")}`;
    input.dataset.variableId = id;
    card.appendChild(input);
    if (variable.definition) {
      const small = document.createElement("small");
      small.textContent = localizeText(variable.definition);
      card.appendChild(small);
    }
    form.appendChild(card);
  });
  $("input-help").textContent = inputVariableIdsForTree(current).length ? "Nhập các thông tin cần thiết; đường đi sẽ sáng lên tương ứng." : "Cây này không yêu cầu dữ liệu đầu vào.";
}

function collectInputs() {
  const values = {};
  document.querySelectorAll("[data-variable-id]").forEach((input) => { if (input.value !== "") values[input.dataset.variableId] = input.value; });
  return values;
}

function refreshTreeOptions() {
  const select = $("tree-select");
  select.innerHTML = "";
  state.bundle.trees.forEach((item) => select.add(new Option(localizeText(item.name || item.id), item.id)));
  select.value = state.treeId;
}

function renderTree() {
  state.previewSequence += 1;
  clearTimeout(state.previewTimer);
  const current = activeTree();
  if (!current) return;
  refreshTreeOptions();
  $("tree-purpose").textContent = localizeText(current.purpose || "");
  $("graph-title").textContent = localizeText(current.name || "Sơ đồ quyết định");
  renderGraph(current);
  renderInputForm(current);
  $("result-box").textContent = "Chưa có kết quả.";
  showStatus("");
  clearPathHighlight();
  const hasDraft = Boolean(state.editedTrees[state.treeId]);
  $("run-draft").disabled = !hasDraft;
  $("graph-title").classList.toggle("draft-active", hasDraft);
}

function setGraphFullscreen(isFullscreen) {
  const panel = $("graph-panel");
  const button = $("fullscreen-graph");
  panel.classList.toggle("is-fullscreen", isFullscreen);
  document.body.classList.toggle("graph-fullscreen", isFullscreen);
  button.textContent = isFullscreen ? "Thu nhỏ" : "Toàn màn hình";
  button.setAttribute("aria-label", isFullscreen ? "Thu nhỏ sơ đồ quyết định" : "Hiển thị cây toàn màn hình");
  button.setAttribute("aria-pressed", String(isFullscreen));
  if (graphInstance) {
    window.setTimeout(() => {
      graphInstance.resize();
      graphInstance.fit(undefined, isFullscreen ? 48 : 36);
    }, 50);
  }
}

function selectTree(treeId, message = "") {
  if (!state.bundle.trees.some((item) => item.id === treeId)) return false;
  state.treeId = treeId;
  renderTree();
  if (message) showStatus(message, "good");
  return true;
}

function renderResult(result) {
  const headline = result.status === "completed"
    ? (result.decision || result.resultCode || result.outcomeCode || "Hoàn tất")
    : result.status === "needs_data"
      ? "Chưa đủ dữ liệu"
      : `Không thể hoàn tất (${result.status || "unknown"})`;
  const lines = [headline];
  if (result.missingData?.length) lines.push(`Cần bổ sung: ${missingVariableLabels(result.missingData).join(", ")}`);
  $("result-box").textContent = lines.join("\n");
  highlightPath(result);
}

function runtimeJobForCurrentTree() { return state.treeJobs[state.treeId]; }
function usesClinicalFlow() { return state.treeId === OPTIMIZED_TREE_ID; }

async function runTree() {
  $("run-tree").disabled = true;
  try {
    const jobId = runtimeJobForCurrentTree();
    const variables = collectInputs();
    const response = usesClinicalFlow()
      ? (state.editedTrees[state.treeId]
        ? await api("/api/run-draft-flow", { method: "POST", body: JSON.stringify({ startTreeId: state.treeId, tree: state.editedTrees[state.treeId], variables }) })
        : await api("/api/run-flow", { method: "POST", body: JSON.stringify({ startTreeId: "bp_thresholds_targets", variables }) }))
      : jobId
        ? await api("/api/pipeline/run", { method: "POST", body: JSON.stringify({ jobId, treeId: state.treeId, variables }) })
        : await api("/api/run", { method: "POST", body: JSON.stringify({ treeId: state.treeId, variables }) });
    renderResult(response.result);
    showStatus("Đã chạy cây quyết định.", "good");
  } catch (error) {
    $("result-box").textContent = error.message;
    showStatus(error.message, "bad");
  } finally {
    $("run-tree").disabled = false;
  }
}

function showDraftStatus(message, kind = "") {
  $("draft-status").textContent = message;
  $("draft-status").className = `status ${kind}`;
}

const nodeTypeLabels = {
  start: "Điểm bắt đầu",
  condition: "Câu hỏi điều kiện",
  inference: "Khuyến nghị / kết luận",
  link: "Liên kết sang cây khác",
  end: "Điểm kết thúc",
};
const operationLabels = {
  eq: "bằng",
  neq: "khác",
  gt: "lớn hơn",
  gte: "lớn hơn hoặc bằng",
  lt: "nhỏ hơn",
  lte: "nhỏ hơn hoặc bằng",
  in: "thuộc một trong",
  not_in: "không thuộc",
  present: "đã có dữ liệu",
};

function workingNode() {
  return state.nodeWorkingTree?.nodes?.find((node) => node.id === state.nodeId);
}

function nodeDisplayTitle(node) {
  return localizeText(node?.display?.title || "Node chưa có tiêu đề");
}

function variableForId(variableId) {
  return state.bundle.variables.find((item) => item.id === variableId);
}

function appendOptions(select, options, selectedValue) {
  options.forEach(([value, label]) => select.add(new Option(label, value, false, value === selectedValue)));
}

function coerceEditorValue(raw, variable) {
  const value = String(raw ?? "").trim();
  if (!value) return null;
  if (variable?.dataType === "boolean") return value === "true";
  if (variable?.dataType === "integer") return Number.parseInt(value, 10);
  if (variable?.dataType === "number") return Number(value);
  return value;
}

function createPredicateValueControl(variable, operation, value) {
  if (operation === "present") return null;
  const isArray = operation === "in" || operation === "not_in";
  if (isArray) {
    const input = document.createElement("input");
    input.className = "condition-value-array";
    input.dataset.arrayValue = "true";
    input.placeholder = "Ví dụ: hypertension, grade1";
    input.value = Array.isArray(value) ? value.join(", ") : "";
    return input;
  }
  if (variable?.dataType === "boolean") {
    const select = document.createElement("select");
    appendOptions(select, [["", "Chưa chọn"], ["true", "Có"], ["false", "Không"]], value == null ? "" : String(value));
    return select;
  }
  if (variable?.dataType === "enum" && variable.allowedValues?.length) {
    const select = document.createElement("select");
    appendOptions(select, [["", "Chưa chọn"], ...variable.allowedValues.map((item) => [item, item])], value == null ? "" : String(value));
    return select;
  }
  const input = document.createElement("input");
  input.type = variable?.dataType === "string" ? "text" : "number";
  if (input.type === "number") input.step = "any";
  input.value = value == null ? "" : String(value);
  return input;
}

function refreshPredicateValue(row, value) {
  const variable = variableForId(row.querySelector(".condition-field").value);
  const operation = row.querySelector(".condition-operation").value;
  const oldValue = value === undefined ? row.querySelector(".condition-value")?.value : value;
  const oldControl = row.querySelector(".condition-value");
  if (oldControl) oldControl.remove();
  const control = createPredicateValueControl(variable, operation, oldValue);
  if (control) {
    control.classList.add("condition-value");
    row.insertBefore(control, row.querySelector(".remove-condition"));
  }
}

function renderPredicate(container, expression = {}) {
  const row = document.createElement("div");
  row.className = "condition-row condition-item";
  row.dataset.conditionKind = "predicate";
  const field = document.createElement("select");
  field.className = "condition-field";
  field.setAttribute("aria-label", "Biến điều kiện");
  appendOptions(field, state.bundle.variables.map((variable) => [variable.id, localizeText(variable.label || variable.id)]), expression.field);
  const operation = document.createElement("select");
  operation.className = "condition-operation";
  operation.setAttribute("aria-label", "Phép so sánh");
  appendOptions(operation, Object.entries(operationLabels), expression.op || "eq");
  row.append(field, operation);
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "secondary remove-condition";
  remove.textContent = "Xóa";
  remove.addEventListener("click", () => row.remove());
  row.appendChild(remove);
  field.addEventListener("change", () => refreshPredicateValue(row, ""));
  operation.addEventListener("change", () => refreshPredicateValue(row, undefined));
  container.appendChild(row);
  refreshPredicateValue(row, expression.value);
}

function renderConditionNode(container, expression, nested = false) {
  const isGroup = expression && (Array.isArray(expression.all) || Array.isArray(expression.any));
  if (!isGroup) {
    renderPredicate(container, expression || {});
    return;
  }
  const group = document.createElement("div");
  group.className = `condition-group condition-item${nested ? " nested" : ""}`;
  group.dataset.conditionKind = "group";
  const head = document.createElement("div");
  head.className = "condition-group-head";
  const selector = document.createElement("select");
  selector.className = "condition-group-operation";
  selector.setAttribute("aria-label", "Cách kết hợp điều kiện");
  appendOptions(selector, [["all", "Tất cả điều kiện"], ["any", "Một trong các điều kiện"]], Array.isArray(expression.any) ? "any" : "all");
  const addRule = document.createElement("button");
  addRule.type = "button";
  addRule.className = "secondary";
  addRule.textContent = "Thêm điều kiện";
  const addGroup = document.createElement("button");
  addGroup.type = "button";
  addGroup.className = "secondary";
  addGroup.textContent = "Thêm nhóm";
  const removeGroup = document.createElement("button");
  removeGroup.type = "button";
  removeGroup.className = "secondary";
  removeGroup.textContent = "Xóa nhóm";
  head.append(selector, addRule, addGroup);
  if (nested) head.appendChild(removeGroup);
  const children = document.createElement("div");
  children.className = "condition-children";
  group.append(head, children);
  const items = Array.isArray(expression.all) ? expression.all : expression.any;
  (items.length ? items : [{ field: state.bundle.variables[0]?.id || "", op: "eq", value: "" }]).forEach((item) => renderConditionNode(children, item, true));
  addRule.addEventListener("click", () => renderPredicate(children, { field: state.bundle.variables[0]?.id || "", op: "eq", value: "" }));
  addGroup.addEventListener("click", () => renderConditionNode(children, { all: [{ field: state.bundle.variables[0]?.id || "", op: "eq", value: "" }] }, true));
  removeGroup.addEventListener("click", () => group.remove());
  selector.addEventListener("change", () => {});
  container.appendChild(group);
}

function readPredicate(row) {
  const variable = variableForId(row.querySelector(".condition-field").value);
  const operation = row.querySelector(".condition-operation").value;
  const predicate = { field: row.querySelector(".condition-field").value, op: operation };
  if (operation === "present") return predicate;
  const control = row.querySelector(".condition-value");
  if (!control) return predicate;
  if (control.dataset.arrayValue === "true") {
    predicate.value = control.value.split(",").map((item) => item.trim()).filter(Boolean).map((item) => coerceEditorValue(item, variable));
  } else {
    predicate.value = coerceEditorValue(control.value, variable);
  }
  return predicate;
}

function readConditionNode(element) {
  if (element.dataset.conditionKind === "predicate") return readPredicate(element);
  const operation = element.querySelector(":scope > .condition-group-head .condition-group-operation").value;
  const children = element.querySelector(":scope > .condition-children");
  return { [operation]: Array.from(children.children).map(readConditionNode) };
}

function renderConditionEditor(node) {
  const panel = $("condition-editor-panel");
  panel.hidden = node?.type !== "condition";
  const builder = $("condition-builder");
  builder.innerHTML = "";
  if (node?.type !== "condition") return;
  const predicate = node.logic?.predicate || { field: state.bundle.variables[0]?.id || "", op: "eq", value: "" };
  renderConditionNode(builder, predicate);
}

function renderLinkEditor(node) {
  const panel = $("link-editor-panel");
  panel.hidden = node?.type !== "link";
  if (node?.type !== "link") return;
  const select = $("node-link-target");
  select.innerHTML = "";
  appendOptions(select, state.bundle.trees.filter((item) => item.id !== state.treeId).map((item) => [item.id, localizeText(item.name || item.id)]), node.data?.targetTreeId);
}

function renderEdgeEditor(node) {
  const builder = $("edge-builder");
  builder.innerHTML = "";
  const edges = (state.nodeWorkingTree?.edges || []).filter((edge) => edge.from === node?.id);
  if (!edges.length) {
    builder.innerHTML = '<div class="condition-empty">Node này không có nhánh đi ra.</div>';
    return;
  }
  edges.forEach((edge, index) => {
    const row = document.createElement("div");
    row.className = "edge-row";
    row.dataset.edgeIndex = String(index);
    const target = state.nodeWorkingTree.nodes.find((item) => item.id === edge.to);
    const branchWhen = edge.when === "default" ? "Mặc định" : localizeText(edge.when || "Mặc định");
    const targetText = `Nhánh ${localizeText(edge.label || branchWhen)}`;
    const targetLabel = document.createElement("span");
    targetLabel.className = "edge-target";
    targetLabel.textContent = `${targetText} → ${nodeDisplayTitle(target)}`;
    const input = document.createElement("input");
    input.className = "edge-label-input";
    input.value = edge.label || "";
    input.placeholder = branchWhen;
    input.setAttribute("aria-label", `Nhãn ${targetText}`);
    row.append(targetLabel, input);
    builder.appendChild(row);
  });
}

function renderNodeSelector() {
  const select = $("node-select");
  select.innerHTML = "";
  (state.nodeWorkingTree?.nodes || []).forEach((node) => {
    select.add(new Option(`${nodeDisplayTitle(node)} · ${nodeTypeLabels[node.type] || node.type}`, node.id, false, node.id === state.nodeId));
  });
}

function loadNodeEditor() {
  const node = workingNode();
  if (!node) return;
  $("node-title").value = node.display?.title || "";
  $("node-detail").value = node.display?.detail || "";
  $("node-type-help").textContent = nodeTypeLabels[node.type] || "Node quyết định";
  renderConditionEditor(node);
  renderLinkEditor(node);
  renderEdgeEditor(node);
}

function saveNodeForm() {
  const node = workingNode();
  if (!node) return;
  node.display = { ...(node.display || {}), title: $("node-title").value.trim() };
  const detail = $("node-detail").value.trim();
  if (detail) node.display.detail = detail;
  else delete node.display.detail;
  if (node.type === "condition") {
    const root = $("condition-builder").firstElementChild;
    if (root) node.logic = { ...(node.logic || {}), predicate: readConditionNode(root) };
  }
  if (node.type === "link") {
    node.data = { ...(node.data || {}), targetTreeId: $("node-link-target").value };
  }
  const outgoing = (state.nodeWorkingTree.edges || []).filter((edge) => edge.from === node.id);
  const rows = Array.from($("edge-builder").querySelectorAll(".edge-row"));
  outgoing.forEach((edge, index) => {
    const label = rows[index]?.querySelector(".edge-label-input")?.value.trim() || "";
    if (label) edge.label = label;
    else delete edge.label;
  });
}

function openEditTree(nodeId = null) {
  const current = activeTree();
  state.nodeWorkingTree = structuredClone(current);
  state.nodeId = nodeId || state.nodeWorkingTree.nodes[0]?.id;
  $("edit-dialog-title").textContent = `Chỉnh sửa: ${localizeText(current?.name || "cây quyết định")}`;
  renderNodeSelector();
  loadNodeEditor();
  $("apply-tree").disabled = true;
  $("save-draft").disabled = true;
  showDraftStatus(state.editedTrees[state.treeId] ? "Đang chỉnh sửa bản nháp đã áp dụng." : "Bản gốc chỉ đọc; các thay đổi sẽ được lưu thành bản nháp.");
  $("edit-tree-dialog").showModal();
}

async function validateEditedTree() {
  saveNodeForm();
  const edited = state.nodeWorkingTree;
  if (!edited) return null;
  try {
    const result = await api("/api/validate-draft", { method: "POST", body: JSON.stringify({ treeId: state.treeId, tree: edited }) });
    if (!result.ok) {
      showDraftStatus((result.errors || ["Cây chưa đạt kiểm tra."]).join("\n"), "bad");
      $("apply-tree").disabled = true;
      $("save-draft").disabled = true;
      return null;
    }
    $("apply-tree").disabled = false;
    $("save-draft").disabled = false;
    showDraftStatus("Thay đổi hợp lệ. Bạn có thể áp dụng xem trước hoặc lưu bản nháp.", "good");
    return edited;
  } catch (error) {
    showDraftStatus(error.message, "bad");
    return null;
  }
}

async function applyEditedTree() {
  const edited = await validateEditedTree();
  if (!edited) return;
  state.editedTrees[state.treeId] = edited;
  $("edit-tree-dialog").close();
  renderTree();
  showStatus("Đã áp dụng bản chỉnh sửa để xem trước. Cây chuẩn chưa bị ghi đè.", "good");
}

async function saveEditedTree() {
  const edited = await validateEditedTree();
  if (!edited) return;
  try {
    const result = await api("/api/save-draft", { method: "POST", body: JSON.stringify({ treeId: state.treeId, tree: edited }) });
    state.editedTrees[state.treeId] = edited;
    $("edit-tree-dialog").close();
    renderTree();
    showStatus(`Đã lưu bản nháp cây ${localizeText(edited.name || edited.id)}.`, "good");
    return result;
  } catch (error) {
    showDraftStatus(error.message, "bad");
    return null;
  }
}

async function runDraft() {
  const edited = state.editedTrees[state.treeId];
  if (!edited) {
    showStatus("Hãy áp dụng bản chỉnh sửa trước khi chạy thử.", "bad");
    return;
  }
  $("run-draft").disabled = true;
  try {
    const variables = collectInputs();
    const response = usesClinicalFlow()
      ? await api("/api/run-draft-flow", { method: "POST", body: JSON.stringify({ startTreeId: state.treeId, tree: edited, variables }) })
      : await api("/api/run-draft", { method: "POST", body: JSON.stringify({ treeId: state.treeId, tree: edited, variables }) });
    renderResult(response.result);
    showStatus("Đã chạy bản chỉnh sửa; cây chuẩn vẫn giữ nguyên.", "good");
  } catch (error) {
    $("result-box").textContent = error.message;
    showStatus(error.message, "bad");
  } finally {
    $("run-draft").disabled = false;
  }
}

function schedulePathPreview() {
  clearTimeout(state.previewTimer);
  const sequence = ++state.previewSequence;
  const variables = collectInputs();
  if (!Object.keys(variables).length) { clearPathHighlight(); return; }
  state.previewTimer = setTimeout(async () => {
    try {
      const jobId = runtimeJobForCurrentTree();
      const response = usesClinicalFlow()
        ? (state.editedTrees[state.treeId]
          ? await api("/api/run-draft-flow", { method: "POST", body: JSON.stringify({ startTreeId: state.treeId, tree: state.editedTrees[state.treeId], variables }) })
          : await api("/api/run-flow", { method: "POST", body: JSON.stringify({ startTreeId: "bp_thresholds_targets", variables }) }))
        : state.editedTrees[state.treeId]
          ? await api("/api/run-draft", { method: "POST", body: JSON.stringify({ treeId: state.treeId, tree: state.editedTrees[state.treeId], variables }) })
          : jobId
            ? await api("/api/pipeline/run", { method: "POST", body: JSON.stringify({ jobId, treeId: state.treeId, variables }) })
            : await api("/api/run", { method: "POST", body: JSON.stringify({ treeId: state.treeId, variables }) });
      if (sequence === state.previewSequence) highlightPath(response.result);
    } catch (error) {
      if (sequence === state.previewSequence) $("path-status").textContent = `Không thể xem đường đi: ${error.message}`;
    }
  }, 180);
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Không thể đọc ảnh."));
    reader.readAsDataURL(file);
  });
}

async function pollPipeline(jobId) {
  const job = await api(`/api/pipeline/jobs/${encodeURIComponent(jobId)}`);
  if (job.status === "queued" || job.status === "running") {
    showPipelineStatus(job.message || "Đang trích xuất ảnh, tạo biến và kiểm tra cây…");
    window.setTimeout(() => pollPipeline(jobId).catch((error) => showPipelineStatus(error.message, "bad")), 1500);
    return;
  }
  if (job.status !== "completed" || !job.bundleReady) {
    showPipelineStatus(job.error || "Pipeline chưa tạo được cây đạt điều kiện kiểm tra.", "bad");
    $("start-pipeline").disabled = false;
    return;
  }
  const generatedBundle = await api(`/api/pipeline/jobs/${encodeURIComponent(jobId)}/bundle`);
  const generatedTree = generatedBundle.trees[0];
  state.bundle.variables = [...new Map([...state.bundle.variables, ...generatedBundle.variables].map((item) => [item.id, item])).values()];
  state.bundle.trees = [...state.bundle.trees.filter((item) => item.id !== generatedTree.id), generatedTree];
  state.runtimeBundles[generatedTree.id] = generatedBundle;
  state.treeJobs[generatedTree.id] = jobId;
  $("new-tree-dialog").close();
  selectTree(generatedTree.id, `Đã tạo và kiểm tra cây: ${localizeText(generatedTree.name || generatedTree.id)}`);
  $("new-tree-form").reset();
  showPipelineStatus("");
  $("start-pipeline").disabled = false;
}

async function createTreeFromImage(event) {
  event.preventDefault();
  const file = $("new-tree-image").files[0];
  if (!file) { showPipelineStatus("Hãy chọn một ảnh guideline.", "bad"); return; }
  $("start-pipeline").disabled = true;
  showPipelineStatus("Đang tải ảnh lên…");
  try {
    const data = await fileToDataUrl(file);
    const name = $("new-tree-name").value.trim();
    const response = await api("/api/pipeline/upload", { method: "POST", body: JSON.stringify({ treeId: makeGeneratedTreeId(name), name, purpose: $("new-tree-purpose").value.trim(), fileName: file.name, mimeType: file.type, data }) });
    showPipelineStatus("Ảnh đã nhận. Đang chạy pipeline…");
    await pollPipeline(response.jobId);
  } catch (error) {
    showPipelineStatus(error.message, "bad");
    $("start-pipeline").disabled = false;
  }
}

async function init() {
  try {
    state.bundle = await api("/api/bundle");
    state.treeId = state.bundle.trees[0].id;
    renderTree();
  } catch (error) {
    showStatus(error.message, "bad");
  }
}

$("tree-select").addEventListener("change", (event) => selectTree(event.target.value));
$("run-tree").addEventListener("click", runTree);
$("run-draft").addEventListener("click", runDraft);
$("input-form").addEventListener("input", schedulePathPreview);
$("input-form").addEventListener("change", schedulePathPreview);
$("clear-input").addEventListener("click", () => { document.querySelectorAll("[data-variable-id]").forEach((input) => { input.value = ""; }); state.previewSequence += 1; clearPathHighlight(); });
$("fit-graph").addEventListener("click", () => { if (graphInstance) graphInstance.fit(undefined, 36); });
$("fullscreen-graph").addEventListener("click", () => setGraphFullscreen(!$("graph-panel").classList.contains("is-fullscreen")));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && $("graph-panel").classList.contains("is-fullscreen")) setGraphFullscreen(false);
});
$("edit-tree").addEventListener("click", () => openEditTree());
$("close-edit-tree").addEventListener("click", () => $("edit-tree-dialog").close());
$("node-select").addEventListener("change", () => {
  saveNodeForm();
  state.nodeId = $("node-select").value;
  loadNodeEditor();
  $("apply-tree").disabled = true;
  $("save-draft").disabled = true;
  showDraftStatus("Bạn có thể tiếp tục chỉnh sửa node, sau đó kiểm tra thay đổi.");
});
$("edit-tree-form").addEventListener("input", () => {
  $("apply-tree").disabled = true;
  $("save-draft").disabled = true;
});
$("validate-tree").addEventListener("click", validateEditedTree);
$("apply-tree").addEventListener("click", applyEditedTree);
$("save-draft").addEventListener("click", saveEditedTree);
$("new-tree-button").addEventListener("click", () => { $("new-tree-dialog").showModal(); });
$("close-new-tree").addEventListener("click", () => $("new-tree-dialog").close());
$("cancel-new-tree").addEventListener("click", () => $("new-tree-dialog").close());
$("new-tree-form").addEventListener("submit", createTreeFromImage);
$("new-tree-image").addEventListener("change", () => {
  const file = $("new-tree-image").files[0];
  $("new-tree-file-name").textContent = file ? file.name : "PNG hoặc JPEG, tối đa 8 MB";
});
init();
