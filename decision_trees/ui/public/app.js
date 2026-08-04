"use strict";

const state = { bundle: null, treeId: null, previewTimer: null, previewSequence: 0 };
const $ = (id) => document.getElementById(id);
const pretty = (value) => JSON.stringify(value, null, 2);
const colors = { start: "#e1fbfb", condition: "#fff8ed", inference: "#dffcf5", link: "#f7d3e6", end: "#dffcf5" };
let graphInstance = null;
let visualEndAliases = new Map();

async function api(url, options = {}) {
  const response = await fetch(url, { headers: { "Content-Type": "application/json" }, ...options });
  const data = await response.json();
  if (!response.ok) throw new Error((data.errors || ["Request failed"]).join("\n"));
  return data;
}

function tree() { return state.bundle.trees.find((item) => item.id === state.treeId); }
function status(message, kind = "") { $("draft-status").textContent = message; $("draft-status").className = `status ${kind}`; }
function resetValidation() { $("save-draft").disabled = true; }

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
    ? `Kết quả: ${result.resultCode || result.outcomeCode || "completed"}`
    : result.status === "needs_data"
      ? `Đang chờ dữ liệu: ${(result.missingData || []).join(", ") || "chưa đủ điều kiện"}`
      : `Trạng thái: ${result.status}`;
  const linkNote = result.terminalTreeId && result.terminalTreeId !== state.treeId ? ` · chuyển đến ${result.terminalTreeId}` : "";
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
    const title = String(node.display?.title || node.type);
    const detail = node.display?.detail || "";
    return { data: { id: node.id, title, detail, nodeType: node.type, label: [title, detail && detail !== title ? detail : ""].filter(Boolean).join("\n") }, classes: node.type };
  });
  const edgeData = current.edges.filter((edge) => !visualEndAliases.has(edge.to)).map((edge, index) => ({ data: { id: `edge-${index}-${edge.from}-${edge.to}`, source: edge.from, target: edge.to, label: edge.label || (edge.when === "default" ? "" : edge.when) }, classes: current.nodes.find((node) => node.id === edge.from)?.type === "link" ? "link-edge" : "" }));
  graphInstance = cytoscape({
    container,
    elements: [...nodeData, ...edgeData],
    style: [
      { selector: "node", style: { "background-color": "data(nodeType)", "background-opacity": 1, "border-color": "#23466f", "border-width": 2, shape: "roundrectangle", width: 230, height: 112, label: "data(label)", color: "#14213b", "font-family": "Inter, ui-sans-serif, system-ui, sans-serif", "font-size": 12, "font-weight": 600, "text-wrap": "wrap", "text-max-width": 202, "text-valign": "center", "text-halign": "center", padding: 8, "overlay-opacity": 0, "shadow-blur": 8, "shadow-color": "#19345a", "shadow-opacity": 0.15, "shadow-offset-x": 0, "shadow-offset-y": 3 } },
      { selector: 'node[nodeType = "start"]', style: { "background-color": colors.start } },
      { selector: 'node[nodeType = "condition"]', style: { "background-color": colors.condition } },
      { selector: 'node[nodeType = "inference"]', style: { "background-color": colors.inference } },
      { selector: 'node[nodeType = "link"]', style: { "background-color": colors.link } },
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
    wheelSensitivity: 0.35,
    minZoom: 0.15,
    maxZoom: 2.2,
  });
  graphInstance.on("tap", "node", (event) => { $("node-inspector").textContent = pretty(current.nodes.find((node) => node.id === event.target.id())); });
}

function renderInputForm(current) {
  const variables = Object.fromEntries(state.bundle.variables.map((item) => [item.id, item])); const form = $("input-form"); form.innerHTML = "";
  (current.inputVariables || []).forEach((id) => { const variable = variables[id]; if (!variable) return; const card = document.createElement("div"); card.className = "input-card"; const label = document.createElement("label"); label.htmlFor = `var-${id.replace(/[^A-Za-z0-9_-]/g, "_")}`; label.textContent = `${variable.label || "Thông tin cần nhập"}${variable.unit ? ` (${variable.unit})` : ""}`; card.appendChild(label);
    let input; if (variable.dataType === "enum" || variable.dataType === "boolean") { input = document.createElement("select"); input.add(new Option("— missing / unknown —", "")); const values = variable.dataType === "boolean" ? ["true", "false"] : (variable.allowedValues || []); values.forEach((value) => input.add(new Option(value, value))); } else { input = document.createElement("input"); input.type = variable.dataType === "string" ? "text" : "number"; if (variable.dataType === "number") input.step = "any"; if (variable.validation?.minimum != null) input.min = variable.validation.minimum; if (variable.validation?.maximum != null) input.max = variable.validation.maximum; }
    input.id = `var-${id.replace(/[^A-Za-z0-9_-]/g, "_")}`; input.dataset.variableId = id; card.appendChild(input); const small = document.createElement("small"); small.textContent = variable.definition || ""; card.appendChild(small); form.appendChild(card); });
  $("input-help").textContent = "Nhập thông tin cần thiết; đường đi trên cây sẽ cập nhật tự động.";
}

function collectInputs() { const values = {}; document.querySelectorAll("[data-variable-id]").forEach((input) => { if (input.value !== "") values[input.dataset.variableId] = input.value; }); return values; }
function renderTree() { state.previewSequence += 1; clearTimeout(state.previewTimer); const current = tree(); $("tree-editor").value = pretty(current); $("node-inspector").textContent = "Click a node to inspect it."; renderGraph(current); renderInputForm(current); resetValidation(); status("Baseline tree loaded. Baseline is read-only from this UI."); $("result-box").textContent = "No run yet."; $("trace-box").textContent = "[]"; $("links-box").textContent = "[]"; $("sources-box").textContent = "[]"; clearPathHighlight(); }

async function validateDraft() { resetValidation(); let edited; try { edited = JSON.parse($("tree-editor").value); } catch (error) { status(`JSON parse error: ${error.message}`, "bad"); return false; } try { const result = await api("/api/validate-draft", { method: "POST", body: JSON.stringify({ treeId: state.treeId, tree: edited }) }); if (!result.ok) { status((result.errors || ["Validation failed"]).join("\n"), "bad"); return false; } $("save-draft").disabled = false; status(`VALID ${JSON.stringify(result.summary)}`, "good"); return true; } catch (error) { status(error.message, "bad"); return false; } }
async function saveDraft() { if (!await validateDraft()) return; try { const result = await api("/api/save-draft", { method: "POST", body: JSON.stringify({ treeId: state.treeId, tree: JSON.parse($("tree-editor").value) }) }); status(`Saved draft riêng:\n${result.treePath}\n${result.bundlePath}`, "good"); } catch (error) { status(error.message, "bad"); } }
function renderResult(result) { $("result-box").textContent = pretty({ status: result.status, resultCode: result.resultCode, outcomeCode: result.outcomeCode, decision: result.decision, missingData: result.missingData || [], context: result.context, sets: result.sets }); $("trace-box").textContent = pretty(result.trace || []); $("links-box").textContent = pretty(result.linksVisited || []); $("sources-box").textContent = pretty(result.sourceRefs || []); highlightPath(result); }
function readEditedTree() { try { return JSON.parse($("tree-editor").value); } catch (error) { status(`JSON parse error: ${error.message}`, "bad"); return null; } }
async function runTree() { $("run-tree").disabled = true; try { const response = await api("/api/run", { method: "POST", body: JSON.stringify({ treeId: state.treeId, variables: collectInputs() }) }); renderResult(response.result); status("Baseline executed. Draft editor không ảnh hưởng baseline.", "good"); } catch (error) { $("result-box").textContent = error.message; } finally { $("run-tree").disabled = false; } }
async function runDraft() { const edited = readEditedTree(); if (!edited) return; $("run-draft").disabled = true; try { const response = await api("/api/run-draft", { method: "POST", body: JSON.stringify({ treeId: state.treeId, tree: edited, variables: collectInputs() }) }); renderResult(response.result); status("Edited draft đã validate và được chạy trên bundle tạm; baseline không bị ghi đè.", "good"); } catch (error) { $("result-box").textContent = error.message; status(error.message, "bad"); } finally { $("run-draft").disabled = false; } }

function schedulePathPreview() {
  clearTimeout(state.previewTimer);
  const sequence = ++state.previewSequence;
  const variables = collectInputs();
  if (!Object.keys(variables).length) { clearPathHighlight(); return; }
  state.previewTimer = setTimeout(async () => {
    try {
      const response = await api("/api/run", { method: "POST", body: JSON.stringify({ treeId: state.treeId, variables }) });
      if (sequence === state.previewSequence) highlightPath(response.result);
    } catch (error) {
      if (sequence === state.previewSequence) $("path-status").textContent = `Không thể preview đường đi: ${error.message}`;
    }
  }, 300);
}

async function init() { try { state.bundle = await api("/api/bundle"); state.treeId = state.bundle.trees[0].id; const select = $("tree-select"); state.bundle.trees.forEach((item) => select.add(new Option(`${item.name || item.id} (${item.id})`, item.id))); $("bundle-meta").textContent = `${state.bundle.bundleId} · v${state.bundle.bundleVersion} · ${state.bundle.trees.length} trees · ${state.bundle.variables.length} variables`; renderTree(); } catch (error) { $("bundle-meta").textContent = error.message; } }
$("tree-select").addEventListener("change", (event) => { state.treeId = event.target.value; renderTree(); }); $("format-json").addEventListener("click", () => { try { $("tree-editor").value = pretty(JSON.parse($("tree-editor").value)); status("JSON formatted. Hãy Validate draft trước khi lưu."); } catch (error) { status(`JSON parse error: ${error.message}`, "bad"); } }); $("validate-draft").addEventListener("click", validateDraft); $("save-draft").addEventListener("click", saveDraft); $("run-tree").addEventListener("click", runTree); $("run-draft").addEventListener("click", runDraft); $("input-form").addEventListener("input", schedulePathPreview); $("input-form").addEventListener("change", schedulePathPreview); $("clear-input").addEventListener("click", () => { document.querySelectorAll("[data-variable-id]").forEach((input) => { input.value = ""; }); state.previewSequence += 1; clearPathHighlight(); }); init();
$("fit-graph").addEventListener("click", () => { if (graphInstance) graphInstance.fit(undefined, 36); });
