# Phát triển DocWeave

Chạy `uv sync` từ thư mục gốc để cài DocWeave và BabelDOC cục bộ.
Thêm mã mới trong `src/docweave/`, kiểm thử trong `tests/`, cấu hình trong
`configs/` và script hỗ trợ trong `scripts/`.

Import BabelDOC qua tên package `babeldoc` như trước. Không thêm đường dẫn
vào `sys.path` trong mã ứng dụng. Cấu hình cài đặt ở `pyproject.toml` chịu
trách nhiệm tìm package trong `third_party/BabelDOC/`.

Chạy kiểm tra cấu trúc và import:

```sh
uv run python -m unittest discover -s tests
uv run babeldoc --help
```

Giữ các thay đổi trong `third_party/BabelDOC/` ở mức cần thiết và ghi rõ lý do.
Khi cập nhật phiên bản BabelDOC, đồng bộ dependency trong `pyproject.toml`
cấp gốc và chạy lại `uv sync`.

Để dùng các lệnh phát triển gốc của BabelDOC, chuyển vào
`third_party/BabelDOC/` trước khi chạy. Hướng dẫn gốc ở
[CONTRIBUTING của BabelDOC](../third_party/BabelDOC/docs/CONTRIBUTING.md).
