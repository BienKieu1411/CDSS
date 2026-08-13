# Decision-tree workspace

Đây là bộ mã và dữ liệu cho các cây tham chiếu cùng bundle JSON dùng cho
runtime CDSS. Hiện bundle kích hoạt đủ Cây 1–5; clinical flow thực thi theo
thứ tự dữ liệu và các cây có thể chuyển tiếp sang cây sau.

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
│   ├── clinical_variables.json             # danh mục biến chuẩn và ánh xạ mã bệnh
│   ├── expected_variable_mapping.json      # ánh xạ tên biến dự kiến trong ảnh sang canonical ID
│   ├── antihypertensive_medication_catalog.json # hoạt chất và nhóm thuốc hạ áp
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
├── trees/                                   # 5 cây độc lập và danh sách biến bàn giao
│   ├── tree_1_bp_diagnosis.json
│   ├── tree_2_bp_thresholds_targets.json
│   ├── tree_3_optimized_hypertension_treatment.json
│   ├── tree_4_hypertension_risk_stratification.json
│   ├── tree_5_uncontrolled_resistant_hypertension.json
│   └── clinical_variables.json
├── tests/                                   # test tự động
│   ├── test_decision_tree_engine.py
│   ├── test_pipeline_guards.py
│   └── run_all_trees.py
├── images/                                  # hình guideline tham chiếu
└── ui/                                      # Node.js workbench
```

Các file không dùng hậu tố `v1`/`v2`; version kỹ thuật nếu cần vẫn nằm trong
metadata JSON hoặc report.

## Kiểm tra

```bash
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

`build_target_bundle.py` là generator legacy cho bộ 5 cây ban đầu; không chạy
file này trong trạng thái hiện tại vì bundle runtime đang được clinical review
và chỉ bật các cây đã được chọn.

`clinical_variables.json` là file tra cứu biến độc lập với ảnh, gồm kiểu dữ
liệu, nguồn dữ liệu, cây sử dụng và quy tắc tự nhận diện ICD-10/SNOMED CT từ
`patient.diagnosisCodes`.

`expected_variable_mapping.json` giữ lớp ánh xạ giữa tên biến trong bảng dự
kiến (ví dụ `sys_bp_first`, `chan_doan_tha`, `ytnc`) và canonical ID dùng trong
bundle/runtime. Các ngưỡng chưa có trong ảnh, như ngưỡng LDL-C/triglyceride,
không được tự suy đoán trong adapter.

`antihypertensive_medication_catalog.json` là danh mục hoạt chất hạ áp dùng
chung. Nhập nhiều hoạt chất trong `medication.currentDrugNames` bằng dấu phẩy
hoặc xuống dòng; engine đọc catalog để sinh danh sách nhóm chuẩn hóa, số nhóm
thuốc và trạng thái có lợi tiểu hay không. Danh sách thuốc encounter trước của
Cây 3 dùng cùng cơ chế này.

`run_all_trees.py` ghi kết quả kiểm thử vào `results/`, mỗi file tương ứng một
`treeId` đang có trong bundle.

Các file trong `trees/` là bản tách để bàn giao: năm cây giữ nguyên node/edge
của bundle đã validate; `clinical_variables.json` chỉ chứa các biến canonical
được ánh xạ từ bảng biến Excel đã thống nhất.
