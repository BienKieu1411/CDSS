#!/usr/bin/env node
"use strict";

/*
 * CDSS local Node.js UI server.
 *
 * Node owns HTTP, draft persistence, and browser presentation. Clinical
 * evaluation and bundle validation remain in the existing Python programs;
 * this server invokes them through child_process and never reimplements their
 * predicate/tree logic.
 */

const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const crypto = require("node:crypto");
const { spawnSync, spawn } = require("node:child_process");
const { URL } = require("node:url");

const UI_DIR = __dirname;
const PROJECT_ROOT = path.resolve(UI_DIR, "../..");
const DECISION_DIR = path.join(PROJECT_ROOT, "decision_trees");
const BUNDLE_PATH = path.join(DECISION_DIR, "bundle", "decision_tree_bundle.json");
const ENGINE_PATH = path.join(DECISION_DIR, "runtime", "decision_tree_engine.py");
const VALIDATOR_PATH = path.join(DECISION_DIR, "runtime", "validate_decision_tree_bundle.py");
const PIPELINE_PATH = path.join(DECISION_DIR, "pipeline", "multi_agent_pipeline.py");
const PYTHON_PATH = process.env.CDSS_PYTHON || process.env.PYTHON || "python3";
const PUBLIC_DIR = path.join(UI_DIR, "public");
const VENDOR_ASSETS = {
  "/vendor/cytoscape.min.js": path.join(UI_DIR, "node_modules", "cytoscape", "dist", "cytoscape.min.js"),
  "/vendor/cytoscape-dagre.min.js": path.join(UI_DIR, "node_modules", "cytoscape-dagre", "dist", "cytoscape-dagre.min.js"),
};
const DRAFTS_DIR = path.join(UI_DIR, "drafts");
const PIPELINE_JOBS_DIR = path.join(UI_DIR, ".pipeline-jobs");
const UPLOADS_DIR = path.join(DECISION_DIR, "images", "uploads");
const MAX_BODY_BYTES = 16 * 1024 * 1024;
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const pipelineJobs = new Map();

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
};

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function writeJson(filePath, value) {
  fs.writeFileSync(filePath, JSON.stringify(value, null, 2) + "\n", "utf8");
}

function loadBundle() {
  return readJson(BUNDLE_PATH);
}

function getTreeMap(bundle) {
  return Object.fromEntries((bundle.trees || []).map((tree) => [tree.id, tree]));
}

function safeTreeId(treeId) {
  if (typeof treeId !== "string" || !/^[A-Za-z0-9_.-]+$/.test(treeId)) {
    throw new Error("treeId contains unsupported characters");
  }
  return treeId;
}

function runPython(scriptPath, args, timeoutMs = 120000) {
  const completed = spawnSync(PYTHON_PATH, [scriptPath, ...args], {
    cwd: DECISION_DIR,
    encoding: "utf8",
    timeout: timeoutMs,
    maxBuffer: 20 * 1024 * 1024,
  });
  if (completed.error) throw completed.error;
  if (completed.status !== 0) {
    const detail = (completed.stderr || completed.stdout || "Python command failed").trim();
    throw new Error(detail.slice(-4000));
  }
  try {
    return JSON.parse(completed.stdout);
  } catch (error) {
    throw new Error(`Python returned invalid JSON: ${error.message}`);
  }
}

function pythonAvailable() {
  const probe = spawnSync(PYTHON_PATH, ["--version"], { cwd: DECISION_DIR, encoding: "utf8" });
  return !probe.error && probe.status === 0;
}

function replaceTree(bundle, treeId, tree) {
  safeTreeId(treeId);
  if (!tree || typeof tree !== "object" || Array.isArray(tree)) throw new Error("tree must be a JSON object");
  if (tree.id !== treeId) throw new Error("edited tree.id must match the selected tree");
  const candidate = structuredClone(bundle);
  const matches = candidate.trees.filter((item) => item.id === treeId);
  if (matches.length !== 1) throw new Error(`unknown tree: ${treeId}`);
  candidate.trees = candidate.trees.map((item) => (item.id === treeId ? structuredClone(tree) : item));
  return candidate;
}

function withTemporaryJson(value, fn) {
  const tempDir = fs.mkdtempSync(path.join(UI_DIR, ".node-runtime-"));
  const tempPath = path.join(tempDir, "candidate.bundle.json");
  try {
    writeJson(tempPath, value);
    return fn(tempPath);
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
}

function validateCandidate(candidate) {
  return withTemporaryJson(candidate, (candidatePath) => runPython(VALIDATOR_PATH, [candidatePath]));
}

function validateTreePayload(treeId, tree) {
  try {
    const summary = validateCandidate(replaceTree(loadBundle(), treeId, tree));
    return { ok: true, treeId, summary };
  } catch (error) {
    return { ok: false, treeId, errors: [error.message] };
  }
}

function saveDraft(treeId, tree) {
  const validation = validateTreePayload(treeId, tree);
  if (!validation.ok) return validation;
  fs.mkdirSync(DRAFTS_DIR, { recursive: true });
  const timestamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  const safeId = safeTreeId(treeId);
  const treePath = path.join(DRAFTS_DIR, `${safeId}.${timestamp}.tree.json`);
  const bundlePath = path.join(DRAFTS_DIR, `${safeId}.${timestamp}.bundle.json`);
  writeJson(treePath, tree);
  writeJson(bundlePath, replaceTree(loadBundle(), treeId, tree));
  return { ...validation, saved: true, treePath, bundlePath };
}

function coerceVariablesForTrees(treeIds, rawVariables, bundle = loadBundle()) {
  if (!rawVariables || typeof rawVariables !== "object" || Array.isArray(rawVariables)) {
    throw new Error("variables must be a JSON object");
  }
  const treeMap = getTreeMap(bundle);
  const inputIds = [...new Set(treeIds.flatMap((treeId) => {
    const currentTree = treeMap[treeId];
    if (!currentTree) throw new Error("unknown tree: " + treeId);
    return currentTree.inputVariables || [];
  }))];
  const variableMap = Object.fromEntries(bundle.variables.map((variable) => [variable.id, variable]));
  const output = {};
  for (const variableId of inputIds) {
    if (!(variableId in rawVariables) || rawVariables[variableId] === "" || rawVariables[variableId] == null) continue;
    const variable = variableMap[variableId];
    if (!variable) throw new Error(`unknown input variable: ${variableId}`);
    const raw = rawVariables[variableId];
    let value;
    if (variable.dataType === "boolean") {
      if (raw === true || String(raw).toLowerCase() === "true") value = true;
      else if (raw === false || String(raw).toLowerCase() === "false") value = false;
      else throw new Error(`${variableId}: expected true or false`);
    } else if (variable.dataType === "integer") {
      if (!/^-?\d+$/.test(String(raw))) throw new Error(`${variableId}: expected integer`);
      value = Number.parseInt(raw, 10);
    } else if (variable.dataType === "number") {
      value = Number(raw);
      if (!Number.isFinite(value)) throw new Error(`${variableId}: expected number`);
    } else if (variable.dataType === "string" || variable.dataType === "enum") {
      value = String(raw);
    } else {
      throw new Error(`${variableId}: unsupported dataType ${variable.dataType}`);
    }
    if (variable.allowedValues && !variable.allowedValues.includes(value)) {
      throw new Error(`${variableId}: value ${JSON.stringify(value)} is not in allowedValues`);
    }
    const rules = variable.validation || {};
    if (typeof value === "number") {
      if (rules.minimum != null && value < rules.minimum) throw new Error(`${variableId}: below minimum ${rules.minimum}`);
      if (rules.maximum != null && value > rules.maximum) throw new Error(`${variableId}: above maximum ${rules.maximum}`);
    }
    output[variableId] = value;
  }
  return output;
}

function coerceVariables(treeId, rawVariables, bundle = loadBundle()) {
  return coerceVariablesForTrees([treeId], rawVariables, bundle);
}

function runEngine(treeId, rawVariables, bundlePath = BUNDLE_PATH) {
  const bundle = bundlePath === BUNDLE_PATH ? loadBundle() : readJson(bundlePath);
  const variables = coerceVariables(treeId, rawVariables, bundle);
  const tempDir = fs.mkdtempSync(path.join(UI_DIR, ".node-runtime-"));
  const inputPath = path.join(tempDir, "input.json");
  try {
    writeJson(inputPath, { variables });
    const result = runPython(ENGINE_PATH, ["--bundle", bundlePath, "--tree-id", treeId, "--input", inputPath]);
    return { variables, result };
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
}

function runClinicalFlow(startTreeId, rawVariables, bundlePath = BUNDLE_PATH) {
  const bundle = bundlePath === BUNDLE_PATH ? loadBundle() : readJson(bundlePath);
  const runtimeStartTreeId = startTreeId === "optimized_hypertension_treatment" ? "bp_thresholds_targets" : startTreeId;
  const flowTreeIds = runtimeStartTreeId === "bp_thresholds_targets"
    ? ["bp_thresholds_targets", "optimized_hypertension_treatment", "uncontrolled_resistant_hypertension"]
    : [runtimeStartTreeId];
  const variables = coerceVariablesForTrees(flowTreeIds, rawVariables, bundle);
  const tempDir = fs.mkdtempSync(path.join(UI_DIR, ".node-runtime-"));
  const inputPath = path.join(tempDir, "input.json");
  try {
    writeJson(inputPath, { variables });
    const result = runPython(ENGINE_PATH, [
      "--bundle", bundlePath,
      "--flow-start-tree-id", runtimeStartTreeId,
      "--input", inputPath,
    ]);
    return { variables, result };
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
}

function runDraftFlow(startTreeId, tree, rawVariables) {
  const validation = validateTreePayload(startTreeId, tree);
  if (!validation.ok) return validation;
  const candidate = replaceTree(loadBundle(), startTreeId, tree);
  const execution = withTemporaryJson(candidate, (candidatePath) => runClinicalFlow(startTreeId, rawVariables, candidatePath));
  return { ok: true, treeId: startTreeId, draftValidation: validation, ...execution };
}

function runDraft(treeId, tree, rawVariables) {
  const validation = validateTreePayload(treeId, tree);
  if (!validation.ok) return validation;
  const candidate = replaceTree(loadBundle(), treeId, tree);
  const execution = withTemporaryJson(candidate, (candidatePath) => runEngine(treeId, rawVariables, candidatePath));
  return { ok: true, treeId, draftValidation: validation, ...execution };
}

function makeJobId() {
  return `${new Date().toISOString().replace(/[-:.TZ]/g, "")}-${crypto.randomBytes(4).toString("hex")}`;
}

function imageExtension(mimeType, fileName) {
  const byMime = { "image/png": ".png", "image/jpeg": ".jpg" };
  if (byMime[mimeType]) return byMime[mimeType];
  const extension = path.extname(String(fileName || "")).toLowerCase();
  if ([".png", ".jpg", ".jpeg"].includes(extension)) return extension === ".jpeg" ? ".jpg" : extension;
  throw new Error("Chỉ hỗ trợ ảnh PNG hoặc JPEG");
}

function decodeUploadedImage(data, mimeType, fileName) {
  if (typeof data !== "string" || !data) throw new Error("Ảnh tải lên không hợp lệ");
  const extension = imageExtension(mimeType, fileName);
  const encoded = data.includes(",") ? data.slice(data.indexOf(",") + 1) : data;
  const buffer = Buffer.from(encoded, "base64");
  if (!buffer.length || buffer.length > MAX_IMAGE_BYTES) throw new Error("Ảnh phải nhỏ hơn 8 MB");
  const isPng = buffer.length >= 8 && buffer.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
  const isJpeg = buffer.length >= 3 && buffer.subarray(0, 3).equals(Buffer.from([255, 216, 255]));
  if ((extension === ".png" && !isPng) || (extension === ".jpg" && !isJpeg)) throw new Error("Nội dung ảnh không khớp định dạng PNG/JPEG");
  return { buffer, extension };
}

function publicPipelineJob(job) {
  return {
    jobId: job.jobId,
    treeId: job.treeId,
    status: job.status,
    message: job.message,
    bundleReady: Boolean(job.bundlePath && fs.existsSync(job.bundlePath)),
    report: job.report ? {
      loopStatus: job.report.loopStatus,
      managerStatus: job.report.managerStatus,
      approvedTreeIds: job.report.approvedTreeIds,
      bundleSummary: job.report.bundleSummary,
      variableStage: job.report.variableStage,
    } : undefined,
    error: job.error,
  };
}

function startPipelineJob(payload) {
  const treeId = safeTreeId(payload.treeId);
  const name = typeof payload.name === "string" ? payload.name.trim() : "";
  const purpose = typeof payload.purpose === "string" ? payload.purpose.trim() : "";
  if (!name || !purpose) throw new Error("Tên cây và mục đích là bắt buộc");
  if (name.length > 200 || purpose.length > 1000) throw new Error("Tên cây hoặc mục đích quá dài");
  const baseline = loadBundle();
  if (getTreeMap(baseline)[treeId] || [...pipelineJobs.values()].some((job) => job.treeId === treeId && ["queued", "running", "completed"].includes(job.status))) {
    throw new Error(`Mã cây đã tồn tại: ${treeId}`);
  }
  const { buffer, extension } = decodeUploadedImage(payload.data, payload.mimeType, payload.fileName);
  const jobId = makeJobId();
  const jobDir = path.join(PIPELINE_JOBS_DIR, jobId);
  const runDir = path.join(jobDir, "run");
  const imageName = `${jobId}${extension}`;
  const imagePath = path.join(UPLOADS_DIR, imageName);
  const manifestPath = path.join(jobDir, "manifest.json");
  fs.mkdirSync(jobDir, { recursive: true });
  fs.mkdirSync(UPLOADS_DIR, { recursive: true });
  fs.writeFileSync(imagePath, buffer);
  writeJson(manifestPath, {
    manifestVersion: "decision-tree-extraction-manifest.v1",
    locale: "vi-VN",
    sources: [{
      treeId,
      sourceId: `upload_${jobId}`,
      file: path.join("uploads", imageName),
      title: name,
      purpose,
    }],
  });
  const job = { jobId, treeId, runDir, manifestPath, status: "queued", message: "Đang xếp hàng chạy pipeline…", output: "" };
  pipelineJobs.set(jobId, job);
  const child = spawn(PYTHON_PATH, [
    PIPELINE_PATH,
    "--manifest", manifestPath,
    "--tree-id", treeId,
    "--out-dir", runDir,
    "--max-rounds", "10",
    "--max-workers", "1",
  ], { cwd: DECISION_DIR, env: { ...process.env, PYTHONUNBUFFERED: "1" } });
  job.status = "running";
  job.message = "Đang trích xuất biến, xây cây và kiểm tra…";
  const appendOutput = (chunk) => { job.output = `${job.output}${chunk}`.slice(-12000); };
  child.stdout.on("data", appendOutput);
  child.stderr.on("data", appendOutput);
  child.on("error", (error) => {
    job.status = "failed";
    job.error = error.message;
    job.message = "Không thể khởi chạy pipeline.";
  });
  child.on("close", (code) => {
    const reportPath = path.join(runDir, "run_report.json");
    const bundlePath = path.join(runDir, "bundle.draft.json");
    if (fs.existsSync(reportPath)) {
      try { job.report = readJson(reportPath); } catch (error) { job.error = error.message; }
    }
    if (fs.existsSync(bundlePath)) job.bundlePath = bundlePath;
    if (code === 0 && job.bundlePath) {
      job.status = "completed";
      job.message = "Đã tạo cây và vượt qua kiểm tra tự động.";
    } else {
      job.status = "failed";
      job.error = job.error || job.report?.nextStep || `Pipeline kết thúc với mã ${code}`;
      job.message = "Cây chưa đạt điều kiện để hiển thị.";
    }
  });
  return publicPipelineJob(job);
}

function getPipelineJob(jobId) {
  const job = pipelineJobs.get(jobId);
  if (!job) throw new Error("Không tìm thấy phiên tạo cây");
  return job;
}

function loadPipelineBundle(jobId) {
  const job = getPipelineJob(jobId);
  if (!job.bundlePath || !fs.existsSync(job.bundlePath)) throw new Error("Cây chưa sẵn sàng");
  return readJson(job.bundlePath);
}

function listDrafts() {
  if (!fs.existsSync(DRAFTS_DIR)) return [];
  return fs.readdirSync(DRAFTS_DIR).filter((name) => name.endsWith(".json")).sort().reverse().slice(0, 100).map((name) => ({
    name,
    path: path.join(DRAFTS_DIR, name),
    kind: name.includes(".bundle.") ? "bundle" : "tree",
  }));
}

function jsonResponse(response, statusCode, value) {
  const body = Buffer.from(JSON.stringify(value, null, 2), "utf8");
  response.writeHead(statusCode, { "Content-Type": "application/json; charset=utf-8", "Content-Length": body.length, "Cache-Control": "no-store" });
  response.end(body);
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    let total = 0;
    const chunks = [];
    request.on("data", (chunk) => {
      total += chunk.length;
      if (total > MAX_BODY_BYTES) {
        reject(new Error("request body is too large"));
        request.destroy();
        return;
      }
      chunks.push(chunk);
    });
    request.on("end", () => {
      try { resolve(JSON.parse(Buffer.concat(chunks).toString("utf8"))); }
      catch (error) { reject(new Error(`invalid JSON body: ${error.message}`)); }
    });
    request.on("error", reject);
  });
}

function serveStatic(response, pathname) {
  const requested = pathname === "/" ? "/index.html" : pathname;
  const filePath = path.resolve(PUBLIC_DIR, `.${requested}`);
  if (!filePath.startsWith(PUBLIC_DIR + path.sep)) return jsonResponse(response, 403, { ok: false, errors: ["Forbidden"] });
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) return jsonResponse(response, 404, { ok: false, errors: ["Not found"] });
  const body = fs.readFileSync(filePath);
  response.writeHead(200, { "Content-Type": MIME[path.extname(filePath)] || "application/octet-stream", "Content-Length": body.length, "Cache-Control": "no-store" });
  response.end(body);
}

function serveVendor(response, pathname) {
  const filePath = VENDOR_ASSETS[pathname];
  if (!filePath || !fs.existsSync(filePath)) return jsonResponse(response, 404, { ok: false, errors: ["Not found"] });
  const body = fs.readFileSync(filePath);
  response.writeHead(200, { "Content-Type": "text/javascript; charset=utf-8", "Content-Length": body.length, "Cache-Control": "no-store" });
  response.end(body);
}

async function handle(request, response) {
  const url = new URL(request.url, `http://${request.headers.host || "localhost"}`);
  try {
    if (request.method === "GET") {
      if (url.pathname === "/api/health") return jsonResponse(response, 200, { ok: true, runtime: "node", python: PYTHON_PATH, bundlePath: BUNDLE_PATH });
      if (url.pathname === "/api/bundle") return jsonResponse(response, 200, loadBundle());
      if (url.pathname === "/api/drafts") return jsonResponse(response, 200, { ok: true, drafts: listDrafts() });
      if (url.pathname.startsWith("/api/pipeline/jobs/")) {
        const parts = url.pathname.split("/").filter(Boolean);
        const jobId = decodeURIComponent(parts[3] || "");
        if (parts[4] === "bundle") return jsonResponse(response, 200, loadPipelineBundle(jobId));
        return jsonResponse(response, 200, { ok: true, ...publicPipelineJob(getPipelineJob(jobId)) });
      }
      if (url.pathname.startsWith("/vendor/")) return serveVendor(response, url.pathname);
      return serveStatic(response, url.pathname);
    }
    if (request.method !== "POST") return jsonResponse(response, 405, { ok: false, errors: ["Method not allowed"] });
    const payload = await readBody(request);
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new Error("request body must be a JSON object");
    if (url.pathname === "/api/validate-draft") return jsonResponse(response, 200, validateTreePayload(payload.treeId, payload.tree));
    if (url.pathname === "/api/save-draft") return jsonResponse(response, 200, saveDraft(payload.treeId, payload.tree));
    if (url.pathname === "/api/run") return jsonResponse(response, 200, { ok: true, ...runEngine(payload.treeId, payload.variables || {}) });
    if (url.pathname === "/api/run-flow") return jsonResponse(response, 200, { ok: true, ...runClinicalFlow(payload.startTreeId || "bp_thresholds_targets", payload.variables || {}) });
    if (url.pathname === "/api/run-draft-flow") {
      const result = runDraftFlow(payload.startTreeId || "optimized_hypertension_treatment", payload.tree, payload.variables || {});
      return jsonResponse(response, result.ok ? 200 : 400, result);
    }
    if (url.pathname === "/api/pipeline/upload") return jsonResponse(response, 202, { ok: true, ...startPipelineJob(payload) });
    if (url.pathname === "/api/pipeline/run") {
      const job = getPipelineJob(payload.jobId);
      if (job.status !== "completed" || !job.bundlePath) throw new Error("Cây mới chưa sẵn sàng để chạy");
      return jsonResponse(response, 200, { ok: true, ...runEngine(payload.treeId, payload.variables || {}, job.bundlePath) });
    }
    if (url.pathname === "/api/run-draft") {
      const result = runDraft(payload.treeId, payload.tree, payload.variables || {});
      return jsonResponse(response, result.ok ? 200 : 400, result);
    }
    return jsonResponse(response, 404, { ok: false, errors: ["Not found"] });
  } catch (error) {
    return jsonResponse(response, 400, { ok: false, errors: [error.message] });
  }
}

function createServer() {
  if (!fs.existsSync(BUNDLE_PATH)) throw new Error(`baseline bundle not found: ${BUNDLE_PATH}`);
  if (!pythonAvailable()) throw new Error(`Python executable is not available: ${PYTHON_PATH}`);
  return http.createServer((request, response) => handle(request, response));
}

function main() {
  const portArg = process.argv.indexOf("--port");
  const port = portArg >= 0 ? Number(process.argv[portArg + 1]) : Number(process.env.PORT || 8501);
  const host = process.env.HOST || "127.0.0.1";
  const server = createServer();
  server.listen(port, host, () => {
    console.log(`CDSS Node UI: http://${host}:${port}`);
    console.log(`Python engine: ${PYTHON_PATH}`);
    console.log(`Baseline bundle: ${BUNDLE_PATH}`);
  });
}

module.exports = { BUNDLE_PATH, PYTHON_PATH, createServer, loadBundle, validateTreePayload, coerceVariables, coerceVariablesForTrees, runEngine, runClinicalFlow, runDraftFlow, runDraft, saveDraft, startPipelineJob, publicPipelineJob };

if (require.main === module) main();
