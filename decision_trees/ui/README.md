# CDSS Decision Tree Workbench

UI local chạy bằng Node.js và gọi Python engine làm nguồn thực thi duy nhất.
UI không sao chép predicate logic sang JavaScript.
Hiện runtime hiển thị đủ Cây 1–5. Dữ liệu người bệnh dùng chung được giữ
trong context; đầu ra của cây trước có thể được dùng bởi cây sau.

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
  kéo và zoom graph.
- Click node liên kết để chuyển chính xác tới cây đích.
- Khi nhập input, UI tự preview kết quả và làm sáng node/edge thuộc đường đi;
  nhánh không được chọn sẽ mờ đi, node đang chờ dữ liệu và node kết thúc có
  trạng thái riêng.
- Tự sinh form input từ `inputVariables`, `dataType`, `allowedValues` và
  `validation`.
- Chạy cây hiện tại bằng engine Python và giữ context để dùng cho bước tiếp theo.

## Kiểm tra

```bash
node --check server.js
node --check public/app.js
npm run smoke
```

## Cấu trúc

```text
ui/
├── server.js          # Node HTTP server và adapter gọi Python engine
├── public/
│   ├── index.html     # layout theo Figma
│   ├── app.js         # graph, form/JSON input, run tree, highlight path
│   └── styles.css     # giao diện theo Figma tokens
├── figma/             # CSS copy từ Figma dùng làm nguồn layout/style
├── package.json
├── package-lock.json
├── node_modules/      # dependency cài bằng npm install
└── test_ui_smoke.js   # smoke test Node + Python engine
```
