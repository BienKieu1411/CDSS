# Decision tree JSON files

Thư mục này chứa năm cây quyết định độc lập và một danh mục biến dùng chung:

- `tree_1_bp_diagnosis.json`
- `tree_2_bp_thresholds_targets.json`
- `tree_3_optimized_hypertension_treatment.json`
- `tree_4_hypertension_risk_stratification.json`
- `tree_5_uncontrolled_resistant_hypertension.json`
- `clinical_variables.json`

Các file cây được tách từ bundle runtime đã kiểm tra. `clinical_variables.json`
là danh mục biến dùng chung cho cả năm cây; các biến dẫn xuất được engine tự
tính từ dữ liệu bệnh nhân, không phải trường nhập thêm.
