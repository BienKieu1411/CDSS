# Contract giữa input/database, decision tree và clinical flow

## Contract và thứ tự tích hợp

Hiện runtime kích hoạt đủ Cây 1–5 theo clinical flow. Các cây có node `LINK`
để hiển thị và điều hướng giữa các giai đoạn; Cây 3 chuyển sang Cây 5 khi
người bệnh đã dùng 4 nhóm thuốc nhưng chưa kiểm soát.

1. Input/database cung cấp patient/encounter context theo `variables` trong [decision_tree_bundle.json](../bundle/decision_tree_bundle.json).
2. Decision-tree layer nhận context, chạy node `CONDITION`, ghi kết quả ở node `INFERENCE` hoặc `END`, và gọi cây con ở node `LINK`.
3. Clinical flow chọn entrypoint theo event và guard trong [trigger_registry.json](./trigger_registry.json).
4. Sau khi chạy, clinical flow lưu decision trace/audit rồi phát event `decision.<treeId>_completed` nếu cần gọi bước tiếp theo.

## Input tối thiểu

```json
{
  "patientId": "patient-123",
  "encounterId": "encounter-456",
  "asOf": "2026-08-03T10:00:00+07:00",
  "variables": {
    "bp.office1.systolicMmHg": 130,
    "bp.office1.diastolicMmHg": 80,
    "bp.office2.systolicMmHg": 130,
    "bp.office2.diastolicMmHg": 80,
    "bp.office3.systolicMmHg": 135,
    "bp.office3.diastolicMmHg": 86,
    "patient.diagnosisCodes": "I25.1, E11.9"
  }
}
```

Các field chưa có dữ liệu phải giữ là `null`/missing, không được tự động đổi thành `false` hoặc `0`. Engine phải trả `missingData` khi node cần dữ liệu chưa có.

## Output chuẩn của engine

```json
{
  "patientId": "patient-123",
  "encounterId": "encounter-456",
  "entryTreeId": "bp_diagnosis",
  "status": "completed",
  "decision": {
    "resultCode": "grade1_htn",
    "sets": { "bp.category": "grade1" },
    "severity": "medium"
  },
  "linksVisited": ["uncontrolled_resistant_hypertension"],
  "trace": [
    { "nodeId": "bp_crisis_gate", "type": "condition", "value": false },
    { "nodeId": "bp_method_office", "type": "condition", "value": true }
  ],
  "sourceRefs": [
    { "sourceId": "image_01_bp_diagnosis", "page": 1, "tableOrFigure": "01_bp_diagnosis.png" }
  ]
}
```

## Quy tắc link giữa các cây

- `LINK` có `targetTreeId`. Link chuyển giai đoạn dùng `callMode: navigate_only`
  để giữ kết quả hiện tại và điều hướng sang cây tiếp theo; link Cây 3 → Cây 5
  dùng `callMode: subtree` để chạy cây con tự động.
- Cây con được phép ghi các biến dẫn xuất như `bp.category` hoặc `risk.class` vào context.
- Engine tự chuẩn hóa `patient.diagnosisCodes` và cập nhật các biến bệnh đồng mắc/tổn thương cơ quan đích theo danh mục trong `clinical_variables.json`.
- Cây 1 ghi `bp.category`; Cây 4 nhận huyết áp lần đo gần nhất và bệnh đồng mắc để ghi `risk.class`; Cây 2 nhận `risk.class` để tạo đích điều trị; Cây 3 nhận đích đó cùng encounter và lịch sử nhóm thuốc; Cây 5 nhận danh sách thuốc hiện tại khi cần phân loại kháng trị.
- Không dùng `LINK` để gọi ngược tạo vòng lặp. Validator phải chặn cycle trong link graph.
- Nếu clinical flow gọi trực tiếp một cây đã được gọi qua `LINK` trong cùng encounter, áp dụng `runPolicy` để tránh chạy trùng.

## Runtime flow hiện có

Local runtime hiện hỗ trợ chạy từng cây active:

```text
Cây 1 (chẩn đoán HA) -> LINK Cây 4 (phân tầng nguy cơ) -> LINK Cây 2
(ngưỡng và đích điều trị) -> LINK Cây 3 (điều trị tối ưu) -> Cây 5
(chưa kiểm soát/kháng trị khi cần)
```

Chạy bằng Python:

```bash
python decision_trees/runtime/decision_tree_engine.py --flow-start-tree-id bp_thresholds_targets --input input.json
```

Node UI giữ context sau mỗi lần chạy để output của Cây 1 được dùng khi chạy
Cây 2. Mapping database/API thuộc adapter layer, không nằm trong JSON cây.

## Mapping với database/API

Database có thể dùng tên field nội bộ khác, nhưng cần một lớp mapping ổn định sang variable ID. Ví dụ:

Danh sách mapping đầy đủ giữa tên biến dự kiến trong bảng nghiên cứu và
canonical ID nằm trong [expected_variable_mapping.json](./expected_variable_mapping.json).

| Variable ID | Nguồn dữ liệu gợi ý | Kiểu |
|---|---|---|
| `bp.office1.systolicMmHg` | encounter.vitals.officeRound1SBP | number, mmHg |
| `bp.office3.systolicMmHg` | encounter.vitals.officeRound3SBP | number, mmHg |
| `bp.latest.systolicMmHg` | engine tự lấy từ cặp HA phòng khám lần 3, nếu thiếu thì lần 2, nếu thiếu thì lần 1 | number, mmHg |
| `bp.latest.diastolicMmHg` | engine tự lấy từ cặp HA phòng khám lần 3, nếu thiếu thì lần 2, nếu thiếu thì lần 1 | number, mmHg |
| `risk.factorCount` | risk-assessment service | integer |
| `risk.highRiskComorbidity` | problem/lab derived risk flag | boolean |
| `encounter.number` | encounter sequence | integer |
| `medication.previousEncounterDrugClassList` | danh sách nhóm thuốc chuẩn hóa từ encounter n-1; dùng `lengthEq/lengthIn` để xác định giai đoạn | array |
| `medication.previousEncounterDrugClassList` | engine chuẩn hóa danh sách thuốc encounter n-1 theo catalog | array |
| `medication.currentDrugClassList` | engine chuẩn hóa danh sách thuốc hiện tại theo catalog | array |
| `treatment.targetSystolicMmHg` | Cây 2 — đích HATT | number, mmHg |
| `treatment.targetDiastolicMmHg` | Cây 2 — đích HATTr | number, mmHg |
| `bp.controlledAfterTwoDrugs` | engine — so sánh HA hiện tại với đích Cây 2 | boolean |
| `bp.controlledAfterThreeDrugs` | engine — so sánh HA hiện tại với đích Cây 2 | boolean |
| `bp.controlledAfterFourDrugs` | engine — so sánh HA hiện tại với đích Cây 2 | boolean |
| `medication.regimenStartDate` | ngày bắt đầu hoặc thay đổi gần nhất của phác đồ từ lịch sử kê đơn | date |
| `medication.regimenStableWeeks` | engine tự tính `floor((asOf - medication.regimenStartDate) / 7 ngày)`; không nhận input ghi đè | number, week |

Mapping không nên nằm trong tree JSON; đặt ở adapter/database layer để guideline logic độc lập với HIS/EMR cụ thể.

## LLM automation có khả thi không?

Có. Nên dùng LLM ở pipeline offline để sinh bản nháp từ guideline:

`PDF/OCR -> đoạn evidence -> LLM extraction -> canonical JSON AST -> schema/semantic validator -> clinical review -> versioned bundle`

## One-shot exemplar

`decision_tree_example.json` and `decision_tree_generation_prompt.md` are generated from the
canonical `bp_diagnosis` tree. They are injected into tree-builder calls
as a format exemplar so that Gemini learns the node/edge/predicate contract in
one shot. The exemplar is format guidance only; builders must derive clinical
thresholds from the target pages and every generated bundle remains
`under_review` until human clinical review.

LLM chỉ được phép sinh:

- node và edge theo schema;
- predicate từ whitelist `eq`, `in`, `gte`, `lt`, `all`, `any` và `valueField` cho so sánh hai biến số;
- variable ID đã tồn tại trong catalog;
- source reference bắt buộc đến page/section/table/figure.

Runtime lâm sàng không nên gọi LLM để tự suy luận lại ngưỡng. Runtime chỉ chạy JSON đã được review, vì vậy hiện tại chưa cần API key. Khi muốn tự động hóa bước sinh nháp, key có thể đặt trong `.env`, nhưng secret không được ghi vào JSON, log hoặc decision trace.

## Checklist để clinical flow dùng được

- [ ] Input adapter map đúng variable IDs và đơn vị.
- [ ] Validate dữ liệu trước khi chạy tree.
- [ ] Chọn event/entrypoint trong `trigger_registry.json`.
- [ ] Chạy tree với `runPolicy` chống trùng.
- [ ] Lưu trace, sourceRefs, bundleVersion và người/engine thực thi.
- [ ] Nếu thiếu dữ liệu hoặc có tình huống critical, chuyển clinician review; không tự fallback sang giá trị mặc định.
