# CDSS Decision Tree

Hệ thống hỗ trợ quyết định lâm sàng gồm bộ 5 cây quyết định, Python engine
để chạy logic và giao diện Node.js để xem/kiểm thử cây.

## Yêu cầu

- Node.js 18 trở lên và npm.
- Python 3.10 trở lên.
- Không cần cài thư viện Python bên ngoài cho runtime hiện tại.

Kiểm tra phiên bản:

```bash
node --version
npm --version
python3 --version
```

## Cài đặt

Từ thư mục gốc dự án:

```bash
cd decision_trees/ui
npm ci
```

`npm ci` cài đúng các phiên bản đã khóa trong `package-lock.json`, gồm:

- `cytoscape`
- `cytoscape-dagre`

Nếu chưa có `package-lock.json` hoặc muốn cập nhật dependency:

```bash
npm install
```

## Chạy giao diện

```bash
cd decision_trees/ui
npm start
```

Mở trình duyệt tại <http://127.0.0.1:8501/>.

Đổi port:

```bash
npm start -- --port 8510
```

Nếu cần chỉ rõ Python executable:

```bash
CDSS_PYTHON=/path/to/python3 npm start -- --port 8510
```

Ví dụ dùng virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
cd decision_trees/ui
npm ci
CDSS_PYTHON=../../.venv/bin/python npm start
```

## Kiểm tra

```bash
cd decision_trees/ui
node --check server.js
node --check public/app.js
npm run smoke
```

Kiểm tra Python engine và bundle:

```bash
cd ../..
python3 decision_trees/runtime/validate_decision_tree_bundle.py
python3 decision_trees/tests/test_pipeline_guards.py
```

## Cấu trúc chính

```text
decision_trees/
├── bundle/decision_tree_bundle.json       # Bundle runtime hiện tại
├── runtime/decision_tree_engine.py        # Python engine
├── trees/                                 # Các cây 1–5 dạng JSON
├── contracts/                             # Catalog thuốc và hợp đồng biến
├── tests/                                 # Test runtime/pipeline
└── ui/
    ├── server.js                          # Node server và API local
    ├── public/app.js                       # Form và hiển thị graph
    ├── public/styles.css                   # Giao diện
    ├── package.json                        # Script/dependency Node.js
    └── package-lock.json                   # Phiên bản dependency cố định
```

UI đọc bundle từ `decision_trees/bundle/decision_tree_bundle.json` và gọi
Python engine khi chạy cây. Các biến kết quả từ cây trước được giữ trong
context để truyền sang các cây liên kết tiếp theo.
