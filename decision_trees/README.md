# Decision-tree workspace

Đây là bộ mã và dữ liệu cho 5 cây tham chiếu trong `images/` cùng bundle JSON
dùng cho runtime CDSS. Các thành phần được tách theo chức năng.

## Cấu trúc

```text
decision_trees/
├── bundle/                                  # JSON/schema/example/prompt
│   ├── decision_tree_bundle.json            # bundle runtime
│   ├── decision_tree_schema.json            # JSON schema
│   ├── decision_tree_pass_criteria.json     # strict pass criteria
│   ├── decision_tree_example.json            # example one-shot chuẩn
│   └── decision_tree_generation_prompt.md   # prompt sinh cây
├── contracts/                               # tích hợp clinical flow
│   ├── clinical_flow_contract.md
│   ├── extraction_manifest.json               # danh sách ảnh đầu vào cho multi-agent
│   └── trigger_registry.json
├── pipeline/                                # Gemini + multi-agent
│   ├── multi_agent_pipeline.py               # ảnh → evidence → variables → trees → verify/repair
│   ├── build_target_bundle.py                # baseline deterministic dùng cho runtime/test
│   ├── generate_decision_tree.py
│   └── create_decision_tree_example.py
├── runtime/                                 # chạy và validate tree
│   ├── decision_tree_engine.py
│   └── validate_decision_tree_bundle.py
├── tests/                                   # test tự động
│   ├── test_decision_tree_engine.py
│   ├── test_pipeline_guards.py
│   └── run_all_trees.py
├── images/                                  # đúng 5 hình mục tiêu
└── ui/                                      # Node.js workbench
```

Các file không dùng hậu tố `v1`/`v2`; version kỹ thuật nếu cần vẫn nằm trong
metadata JSON hoặc report.

## Kiểm tra

```bash
python decision_trees/pipeline/build_target_bundle.py
python decision_trees/runtime/validate_decision_tree_bundle.py
python decision_trees/tests/test_decision_tree_engine.py
python decision_trees/tests/test_pipeline_guards.py
python decision_trees/pipeline/create_decision_tree_example.py
python decision_trees/tests/run_all_trees.py

cd decision_trees/ui
npm run smoke
```

Pipeline đa tác tử đọc `contracts/extraction_manifest.json`, gửi từng ảnh mục
tiêu cho các evidence agents, chạy variable agents theo từng cây, hợp nhất
catalog, sinh tree song song và lặp verifier/repair tối đa 10 vòng. Pipeline
không đọc baseline bundle để làm template và không tự ghi đè baseline; kết quả
đạt strict gate được ghi thành `runs/<timestamp>/bundle.draft.json` để clinical
review.

`build_target_bundle.py` chỉ tạo lại baseline deterministic đã được review để
phục vụ runtime/test. Nó không được gọi trong luồng multi-agent extraction.

`run_all_trees.py` ghi kết quả kiểm thử vào `results/`, mỗi file tương ứng một
`treeId` trong bundle.
