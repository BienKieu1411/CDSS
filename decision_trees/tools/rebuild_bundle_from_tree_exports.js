const fs = require("fs");

const bundlePath = "decision_trees/bundle/decision_tree_bundle.json";
const variablesPath = "decision_trees/contracts/clinical_variables.json";
const treeDir = "decision_trees/trees";

function readJson(path) {
  return JSON.parse(fs.readFileSync(path, "utf8"));
}

function writeJson(path, value) {
  fs.writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
}

const bundle = readJson(bundlePath);
const contracts = readJson(variablesPath);
const treeFiles = fs.readdirSync(treeDir)
  .filter((name) => /^tree_[1-5]_.+\.json$/.test(name))
  .sort();

if (treeFiles.length !== 5) {
  throw new Error(`Expected five exported trees, found ${treeFiles.length}`);
}

bundle.variables = contracts.variables;
bundle.trees = treeFiles.map((name) => readJson(`${treeDir}/${name}`).tree);
writeJson(bundlePath, bundle);

console.log(JSON.stringify({ status: "ok", trees: bundle.trees.length, variables: bundle.variables.length }));
