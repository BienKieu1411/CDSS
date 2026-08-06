# CDSS Decision Tree Workbench

UI local chạy bằng Node.js và gọi Python engine/validator làm nguồn thực thi
duy nhất. UI không sao chép predicate logic sang JavaScript. Chạy baseline
không cần API key; chức năng tạo cây mới từ ảnh cần `GEMINI_KEY` trong môi
trường chạy server.
Flow liên kết Cây 2 → Cây 3 → Cây 5 được thực thi qua endpoint nội bộ
`POST /api/run-flow`; output đích HA của Cây 2 được truyền tự động vào Cây 3.

## Cài dependency và chạy

```bash
cd decision_trees/ui
npm install
node server.js
```

Mở <http://127.0.0.1:8501>.

Có thể đổi port hoặc chỉ rõ Python:

```bash
node server.js --port 8510
CDSS_PYTHON=/path/to/python node server.js
```

## Chức năng

- Xem graph của các decision tree bằng Cytoscape.js + cytoscape-dagre; hỗ trợ
  kéo, zoom và căn chỉnh graph.
- Click node liên kết để chuyển chính xác tới cây đích.
- Khi nhập input, UI tự preview kết quả và làm sáng node/edge thuộc đường đi;
  nhánh không được chọn sẽ mờ đi, node đang chờ dữ liệu và node kết thúc có
  trạng thái riêng.
- Tự sinh form input từ `inputVariables`, `dataType`, `allowedValues` và
  `validation`.
- Mở chế độ chỉnh sửa node trực quan để sửa tiêu đề, mô tả, điều kiện, nhãn
  nhánh và liên kết; có thể kiểm tra, áp dụng xem trước, chạy thử và lưu bản
  nháp riêng. Bundle chuẩn không bị ghi đè.
- Upload ảnh guideline, nhập tên/mục đích, rồi chạy pipeline extract biến →
  build tree → verify/repair. Cây chỉ được thêm vào UI khi pipeline tạo được
  `bundle.draft.json` đạt validator.

## Kiểm tra

```bash
node --check server.js
node --check public/app.js
npm run smoke
```

## Cấu trúc

```text
ui/
├── server.js          # Node HTTP server và adapter gọi Python
├── public/
│   ├── index.html     # layout
│   ├── app.js         # Cytoscape graph, input form, upload pipeline, result
│   └── styles.css     # giao diện
├── package.json
├── package-lock.json
├── node_modules/      # dependency cài bằng npm install
├── test_ui_smoke.js   # smoke test Node + Python engine/validator
└── .pipeline-jobs/    # tự tạo khi chạy pipeline upload ảnh
```
