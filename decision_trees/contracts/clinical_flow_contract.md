# Contract giữa input/database, decision tree và clinical flow

## Contract và thứ tự tích hợp

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
    "bp.measurementMethod": "office_3rd",
    "bp.office1.systolicMmHg": 130,
    "bp.office1.diastolicMmHg": 80,
    "bp.office3.systolicMmHg": 135,
    "bp.office3.diastolicMmHg": 86
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

- `LINK` có `targetTreeId`; engine push context hiện tại vào stack và chạy cây con.
- Cây con được phép ghi các biến dẫn xuất như `bp.category` hoặc `risk.class` vào context.
- Khi cây con kết thúc, engine merge `sets`, `resultCode`, `severity` và `trace` về cây cha.
- Không dùng `LINK` để gọi ngược tạo vòng lặp. Validator phải chặn cycle trong link graph.
- Nếu clinical flow gọi trực tiếp một cây đã được gọi qua `LINK` trong cùng encounter, áp dụng `runPolicy` để tránh chạy trùng.

## Mapping với database/API

Database có thể dùng tên field nội bộ khác, nhưng cần một lớp mapping ổn định sang variable ID. Ví dụ:

| Variable ID | Nguồn dữ liệu gợi ý | Kiểu |
|---|---|---|
| `bp.office1.systolicMmHg` | encounter.vitals.officeRound1SBP | number, mmHg |
| `bp.office3.systolicMmHg` | encounter.vitals.officeRound3SBP | number, mmHg |
| `bp.home.systolicMmHg` | patient.homeBloodPressure.SBP | number, mmHg |
| `bp.abpm.daytime.systolicMmHg` | monitoring.abpm.daytimeSBP | number, mmHg |
| `risk.factorCount` | risk-assessment service | integer |
| `risk.highRiskComorbidity` | problem/lab derived risk flag | boolean |
| `medication.agentCount` | medication reconciliation | integer |
| `resistant.exclusionCriteriaPresent` | safety-screen service | boolean |

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
- predicate từ whitelist `eq`, `in`, `gte`, `lt`, `all`, `any`;
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
