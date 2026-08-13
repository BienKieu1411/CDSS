const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const bundlePath = path.join(root, "bundle", "decision_tree_bundle.json");
const variablesPath = path.join(root, "contracts", "clinical_variables.json");
const mappingPath = path.join(root, "contracts", "expected_variable_mapping.json");
const outputDir = path.join(root, "trees");
const bundle = JSON.parse(fs.readFileSync(bundlePath, "utf8"));
const variables = JSON.parse(fs.readFileSync(variablesPath, "utf8"));
const mapping = JSON.parse(fs.readFileSync(mappingPath, "utf8"));
const sharedVariableIds = new Set([
  ...mapping.independent,
  ...mapping.dependent,
].map((item) => item.canonicalId));
const treeVariableIds = new Set(bundle.trees.flatMap((tree) => [
  ...(tree.inputVariables || []),
  ...(tree.outputVariables || []),
]));

fs.mkdirSync(outputDir, { recursive: true });

const fileNames = {
  bp_diagnosis: "tree_1_bp_diagnosis.json",
  bp_thresholds_targets: "tree_2_bp_thresholds_targets.json",
  optimized_hypertension_treatment: "tree_3_optimized_hypertension_treatment.json",
  hypertension_risk_stratification: "tree_4_hypertension_risk_stratification.json",
  uncontrolled_resistant_hypertension: "tree_5_uncontrolled_resistant_hypertension.json",
};

for (const tree of bundle.trees) {
  const fileName = fileNames[tree.id];
  if (!fileName) throw new Error(`No file name configured for ${tree.id}`);
  fs.writeFileSync(path.join(outputDir, fileName), `${JSON.stringify({
    formatVersion: "decision-tree.v1",
    tree,
  }, null, 2)}\n`);
}

fs.writeFileSync(path.join(outputDir, "clinical_variables.json"), `${JSON.stringify({
  formatVersion: "clinical-variable-catalog.v1",
  locale: variables.locale,
  source: "expected_variable_mapping.json",
  // Keep the agreed shared catalog and every variable explicitly consumed or
  // produced by one of the five active trees.
  variables: variables.variables.filter((variable) => sharedVariableIds.has(variable.id) || treeVariableIds.has(variable.id)),
}, null, 2)}\n`);

console.log(JSON.stringify({
  status: "ok",
  outputDir,
  files: [...Object.values(fileNames), "clinical_variables.json"],
}, null, 2));
