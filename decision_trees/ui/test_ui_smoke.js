#!/usr/bin/env node
"use strict";

const assert = require("node:assert/strict");
const http = require("node:http");
const { createServer, loadBundle, runEngine, runClinicalFlow, missingRequiredVariables } = require("./server.js");

function request(port, method, pathname, payload) {
  return new Promise((resolve, reject) => {
    const body = payload === undefined ? "" : JSON.stringify(payload);
    const request = http.request({ hostname: "127.0.0.1", port, path: pathname, method, headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) } }, (response) => {
      let text = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => { text += chunk; });
      response.on("end", () => {
        if (response.headers["content-type"]?.startsWith("text/html") || response.headers["content-type"]?.startsWith("text/javascript") || response.headers["content-type"]?.startsWith("text/css") || response.headers["content-type"]?.startsWith("image/")) {
          resolve({ status: response.statusCode, body: text });
          return;
        }
        try { resolve({ status: response.statusCode, body: JSON.parse(text) }); }
        catch (error) { reject(error); }
      });
    });
    request.on("error", reject);
    request.end(body);
  });
}

async function main() {
  const bundle = loadBundle();
  assert.equal(bundle.trees.length, 5);
  const bp = bundle.trees.find((item) => item.id === "bp_diagnosis");
  assert.ok(bp);
  assert.ok(bundle.trees.find((item) => item.id === "hypertension_risk_stratification"));
  assert.ok(bundle.trees.find((item) => item.id === "optimized_hypertension_treatment"));
  assert.ok(bundle.trees.find((item) => item.id === "uncontrolled_resistant_hypertension"));

  const input = {
    "bp.office.measurement1.systolicMmHg": "130",
    "bp.office.measurement1.diastolicMmHg": "80",
    "bp.office.measurement2.systolicMmHg": "130",
    "bp.office.measurement2.diastolicMmHg": "80",
    "bp.office.measurement3.systolicMmHg": "120",
    "bp.office.measurement3.diastolicMmHg": "80",
    "patient.conditionCodes": "NO_KNOWN_CODES",
  };
  const run = runEngine(bp.id, input);
  assert.equal(run.result.status, "completed");
  assert.equal(run.result.outcomeCode, "normal_bp");
  assert.ok(Array.isArray(run.result.trace));
  assert.deepEqual(missingRequiredVariables([bp.id], input, bundle), []);
  const incomplete = runEngine(bp.id, { "bp.office.measurement1.systolicMmHg": 130 }, { strict: true });
  assert.equal(incomplete.result.status, "needs_data");
  assert.ok(incomplete.result.missingData.includes("bp.office.measurement1.diastolicMmHg"));

  const flowInput = {
    "hypertension.diagnosisCategory": "high_normal_bp",
    "encounter.number": 1,
    "patient.birthDate": "1990-01-01",
    "patient.conditionCodes": "NO_KNOWN_CODES",
  };
  const flow = runClinicalFlow("bp_thresholds_targets", flowInput);
  assert.equal(flow.result.terminalTreeId, "bp_thresholds_targets");
  assert.equal(flow.result.outcomeCode, "lifestyle_change_and_recheck");

  const defaultFlow = runClinicalFlow(undefined, { "bp.office.measurement1.systolicMmHg": 130 });
  assert.equal(defaultFlow.result.entryTreeId, "bp_diagnosis");
  assert.equal(defaultFlow.result.status, "needs_data");

  const port = 18765;
  const server = createServer();
  await new Promise((resolve) => server.listen(port, "127.0.0.1", resolve));
  try {
    const health = await request(port, "GET", "/api/health");
    assert.equal(health.status, 200);
    assert.equal(health.body.runtime, "node");

    const page = await request(port, "GET", "/");
    assert.equal(page.status, 200);
    assert.match(page.body, /Clinical Decision Support System/);
    assert.match(page.body, /Tree Tester/);
    assert.match(page.body, /Tree Explorer/);
    assert.match(page.body, /Tree Builder/);
    assert.match(page.body, /Dynamic form/);
    assert.match(page.body, /json-input/);
    assert.match(page.body, /json-file/);
    assert.match(page.body, /Dữ liệu dùng chung/);
    assert.match(page.body, /zoom-in/);
    assert.match(page.body, /zoom-out/);
    assert.match(page.body, /vendor\/cytoscape\.min\.js/);
    assert.match(page.body, /path-status/);
    assert.match(page.body, /language-toggle/);
    assert.match(page.body, /Patient Simulator|Mô phỏng người bệnh/);
    assert.match(page.body, /start-traversal/);
    assert.match(page.body, /preset-select/);
    assert.match(page.body, /patient-tab-history/);
    assert.match(page.body, /new-tree-button/);
    assert.match(page.body, /import-tree-file/);
    assert.match(page.body, /export-tree-button/);
    assert.match(page.body, /builder-search/);
    assert.match(page.body, /builder-node-label/);
    assert.match(page.body, /builder-node-type/);
    assert.match(page.body, /builder-node-detail/);
    assert.match(page.body, /explorer-search/);
    assert.match(page.body, /explorer-options/);
    assert.doesNotMatch(page.body, /NO LLM · NO API KEY/);
    assert.doesNotMatch(page.body, /Node\.js local UI/);
    const styles = await request(port, "GET", "/styles.css");
    assert.equal(styles.status, 200);
    assert.match(styles.body, /\.tester-sidebar[\s\S]*overflow-y: auto/);
    assert.match(styles.body, /\.tester-actions-footer/);
    assert.doesNotMatch(styles.body, /\.simulator-actions\s*\{[\s\S]*position:\s*sticky/);
    const cytoscapeAsset = await request(port, "GET", "/vendor/cytoscape.min.js");
    assert.equal(cytoscapeAsset.status, 200);
    assert.match(cytoscapeAsset.body, /Cytoscape/);
    const medicationCatalog = await request(port, "GET", "/api/medication-catalog");
    assert.equal(medicationCatalog.status, 200);
    assert.equal(medicationCatalog.body.classes.length, 7);
    for (const icon of ["logo_app.png", "logo_visual.png", "tree_builder_icon.png", "tree_explorer_icon.png", "tree_tester_icon.png", "language_en.svg", "language_vi.svg"]) {
      const asset = await request(port, "GET", `/icon/${icon}`);
      assert.equal(asset.status, 200);
      assert.equal(asset.body.length > 0, true);
    }

    const runApi = await request(port, "POST", "/api/run", {
      treeId: bp.id,
      patientId: "patient-smoke",
      asOf: "2026-08-11",
      variables: input,
    });
    assert.equal(runApi.status, 200);
    assert.equal(runApi.body.result.outcomeCode, "normal_bp");
    assert.equal(runApi.body.result.patientId, "patient-smoke");
    assert.equal(runApi.body.result.asOf, "2026-08-11");

    const flowApi = await request(port, "POST", "/api/run-flow", { startTreeId: "bp_thresholds_targets", variables: flowInput });
    assert.equal(flowApi.status, 200);
    assert.equal(flowApi.body.result.terminalTreeId, "bp_thresholds_targets");
    assert.equal(flowApi.body.result.outcomeCode, "lifestyle_change_and_recheck");

    const removedDraftApi = await request(port, "POST", "/api/run-draft", { treeId: bp.id, tree: bp, variables: input });
    assert.equal(removedDraftApi.status, 404);

    const removedPipelineApi = await request(port, "POST", "/api/pipeline/upload", {});
    assert.equal(removedPipelineApi.status, 404);

    console.log(JSON.stringify({ status: "ok", node: process.version, trees: bundle.trees.length, resultCode: run.result.resultCode }));
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
