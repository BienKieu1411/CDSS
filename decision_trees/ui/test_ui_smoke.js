#!/usr/bin/env node
"use strict";

const assert = require("node:assert/strict");
const http = require("node:http");
const { createServer, loadBundle, validateTreePayload, runEngine, runDraft } = require("./server.js");

function request(port, method, pathname, payload) {
  return new Promise((resolve, reject) => {
    const body = payload === undefined ? "" : JSON.stringify(payload);
    const request = http.request({ hostname: "127.0.0.1", port, path: pathname, method, headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) } }, (response) => {
      let text = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => { text += chunk; });
      response.on("end", () => {
        if (response.headers["content-type"]?.startsWith("text/html") || response.headers["content-type"]?.startsWith("text/javascript")) {
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

  const validation = validateTreePayload(bp.id, bp);
  assert.equal(validation.ok, true, JSON.stringify(validation));

  const input = {
    "bp.measurementMethod": "office_3rd",
    "bp.office1.systolicMmHg": "130",
    "bp.office1.diastolicMmHg": "80",
    "bp.office1.targetOrganDamageOrCvd": "false",
    "bp.office2.systolicMmHg": "130",
    "bp.office2.diastolicMmHg": "80",
    "bp.office2.targetOrganDamageOrCvd": "false",
    "bp.office3.systolicMmHg": "120",
    "bp.office3.diastolicMmHg": "80",
  };
  const run = runEngine(bp.id, input);
  assert.equal(run.result.status, "completed");
  assert.equal(run.result.resultCode, "normal_bp");
  assert.ok(Array.isArray(run.result.trace));

  const draftRun = runDraft(bp.id, bp, input);
  assert.equal(draftRun.ok, true, JSON.stringify(draftRun));
  assert.equal(draftRun.result.resultCode, "normal_bp");

  const port = 18765;
  const server = createServer();
  await new Promise((resolve) => server.listen(port, "127.0.0.1", resolve));
  try {
    const health = await request(port, "GET", "/api/health");
    assert.equal(health.status, 200);
    assert.equal(health.body.runtime, "node");

    const page = await request(port, "GET", "/");
    assert.equal(page.status, 200);
    assert.match(page.body, /Cây quyết định/);
    assert.match(page.body, /vendor\/cytoscape\.min\.js/);
    assert.match(page.body, /path-status/);
    assert.match(page.body, /new-tree-button/);
    assert.match(page.body, /new-tree-image/);
    assert.match(page.body, /Tạo cây mới từ ảnh/);
    assert.match(page.body, /edit-tree/);
    assert.match(page.body, /fullscreen-graph/);
    assert.match(page.body, /Toàn màn hình/);
    assert.match(page.body, /node-select/);
    assert.match(page.body, /condition-builder/);
    assert.match(page.body, /validate-tree/);
    assert.match(page.body, /Chỉnh sửa cây/);
    assert.match(page.body, /run-draft/);
    assert.doesNotMatch(page.body, /tree-editor/);
    assert.doesNotMatch(page.body, /node-inspector/);
    assert.doesNotMatch(page.body, /Source references/);
    assert.doesNotMatch(page.body, /Trace/);
    assert.doesNotMatch(page.body, /Format JSON/);
    assert.doesNotMatch(page.body, /NO LLM · NO API KEY/);
    assert.doesNotMatch(page.body, /Node\.js local UI/);
    const cytoscapeAsset = await request(port, "GET", "/vendor/cytoscape.min.js");
    assert.equal(cytoscapeAsset.status, 200);
    assert.match(cytoscapeAsset.body, /Cytoscape/);

    const runApi = await request(port, "POST", "/api/run", { treeId: bp.id, variables: input });
    assert.equal(runApi.status, 200);
    assert.equal(runApi.body.result.resultCode, "normal_bp");

    const draftApi = await request(port, "POST", "/api/validate-draft", { treeId: bp.id, tree: bp });
    assert.equal(draftApi.status, 200);
    assert.equal(draftApi.body.ok, true);

    const runDraftApi = await request(port, "POST", "/api/run-draft", { treeId: bp.id, tree: bp, variables: input });
    assert.equal(runDraftApi.status, 200);
    assert.equal(runDraftApi.body.result.resultCode, "normal_bp");

    const uploadValidation = await request(port, "POST", "/api/pipeline/upload", {});
    assert.equal(uploadValidation.status, 400);
    assert.match(uploadValidation.body.errors[0], /treeId/);

    const missingJob = await request(port, "GET", "/api/pipeline/jobs/unknown-job");
    assert.equal(missingJob.status, 400);
    assert.match(missingJob.body.errors[0], /Không tìm thấy/);

    console.log(JSON.stringify({ status: "ok", node: process.version, trees: bundle.trees.length, resultCode: run.result.resultCode }));
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
