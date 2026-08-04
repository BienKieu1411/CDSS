# CDSS Decision Tree Workbench

UI local chạy bằng Node.js và gọi Python engine/validator làm nguồn thực thi
duy nhất. UI không sao chép predicate logic sang JavaScript và không cần API
key.

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

- Xem graph của 5 decision tree bằng Cytoscape.js + cytoscape-dagre, gồm node,
  edge và `LINK`; hỗ trợ kéo, zoom và căn chỉnh graph.
- Khi nhập input, UI tự preview kết quả và làm sáng node/edge thuộc đường đi;
  nhánh không được chọn sẽ mờ đi, node đang chờ dữ liệu và node kết thúc có
  trạng thái riêng.
- Click node để xem chi tiết JSON.
- Chỉnh sửa JSON tree; validator chỉ chạy trên bản copy tạm.
- Chỉ cho lưu draft sau khi validator pass; baseline không bị ghi đè.
- Lưu `*.tree.json` và `*.bundle.json` tại `drafts/`.
- Tự sinh form input từ `inputVariables`, `dataType`, `allowedValues` và
  `validation`.
- Chạy input trên baseline hoặc trực tiếp trên tree draft đang chỉnh sửa.
- Hiển thị decision, missing data, trace, links và source references.

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
│   ├── app.js         # Cytoscape graph, editor, input form, result
│   └── styles.css     # giao diện
├── package.json
├── package-lock.json
├── node_modules/      # dependency cài bằng npm install
├── test_ui_smoke.js   # smoke test Node + Python engine/validator
└── drafts/            # tự tạo khi người dùng lưu draft
```
