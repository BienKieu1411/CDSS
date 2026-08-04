"""Canonical paths for the decision-tree workspace."""

from pathlib import Path


DECISION_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DECISION_ROOT.parent

BUNDLE_DIR = DECISION_ROOT / "bundle"
CONTRACTS_DIR = DECISION_ROOT / "contracts"
PIPELINE_DIR = DECISION_ROOT / "pipeline"
RUNTIME_DIR = DECISION_ROOT / "runtime"
TESTS_DIR = DECISION_ROOT / "tests"
IMAGES_DIR = DECISION_ROOT / "images"
UI_DIR = DECISION_ROOT / "ui"
RUNS_DIR = DECISION_ROOT / "runs"

BUNDLE_PATH = BUNDLE_DIR / "decision_tree_bundle.json"
SCHEMA_PATH = BUNDLE_DIR / "decision_tree_schema.json"
PASS_CRITERIA_PATH = BUNDLE_DIR / "decision_tree_pass_criteria.json"
EXAMPLE_PATH = BUNDLE_DIR / "decision_tree_example.json"
GENERATION_PROMPT_PATH = BUNDLE_DIR / "decision_tree_generation_prompt.md"
TRIGGER_REGISTRY_PATH = CONTRACTS_DIR / "trigger_registry.json"
SOURCE_PDF_PATH = PROJECT_ROOT / "Khuyến cáo THA VNHA 2022.pdf"
