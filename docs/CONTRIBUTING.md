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

Chạy web bằng `uv run docweave`. Phần web nằm trong `src/docweave/`:
`app.py` nhận yêu cầu, `jobs.py` quản lý hàng đợi/SQLite, `worker.py` gọi
BabelDOC ở subprocess, `static/` chứa giao diện không cần bước build JavaScript.

`tests/test_web.py` dùng tiến trình giả lập cho phần dịch, kiểm tra hợp đồng
HTTP và vòng đời tác vụ mà không gửi yêu cầu dịch trả phí. Chạy
`uv run python scripts/check_core.py` để kiểm tra pipeline BabelDOC thật với
dịch vụ phản hồi cố định trên localhost. Không coi kiểm tra này là đánh giá
chất lượng dịch của nhà cung cấp.

Thay đổi tích hợp trong fork: `babeldoc/const.py` hỗ trợ `BABELDOC_CACHE_DIR`
để đặt cache model/font trong thư mục dữ liệu ứng dụng, không đổi thư mục home
của tiến trình. Nếu không đặt biến này, hành vi BabelDOC CLI giữ nguyên.

Giữ các thay đổi trong `third_party/BabelDOC/` ở mức cần thiết và ghi rõ lý do.
Khi cập nhật phiên bản BabelDOC, đồng bộ dependency trong `pyproject.toml`
cấp gốc và chạy lại `uv sync`.

Để dùng các lệnh phát triển gốc của BabelDOC, chuyển vào
`third_party/BabelDOC/` trước khi chạy. Hướng dẫn gốc ở
[CONTRIBUTING của BabelDOC](../third_party/BabelDOC/docs/CONTRIBUTING.md).
