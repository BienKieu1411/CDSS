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
│   └── trigger_registry.json
├── pipeline/                                # Gemini + multi-agent
│   ├── multi_agent_pipeline.py
│   ├── build_target_bundle.py                # deterministic image-target bundle builder
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

Pipeline đa tác tử có thể gửi trực tiếp 5 ảnh mục tiêu vào Gemini; các vòng
verify/repair được giới hạn theo file pass criteria. Artifact chạy thử nếu có
phải nằm ngoài baseline bundle.

`run_all_trees.py` ghi kết quả kiểm thử vào `results/`, mỗi file tương ứng một
`treeId` trong bundle.
