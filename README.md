# DocWeave

Ứng dụng web dịch PDF bằng BabelDOC: tải tài liệu lên, chọn ngôn ngữ, theo dõi
tiến độ và tải PDF bản dịch hoặc song ngữ. Giao diện tiếng Việt, không cần Node.js.

## Chạy ứng dụng web

Cần Python 3.10–3.13 và `uv`. Từ thư mục gốc repo:

```sh
uv sync --locked
uv run docweave
```

Mở **http://127.0.0.1:8000**. Trên PowerShell cũng có thể chạy:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

Chọn PDF, chọn ngôn ngữ gốc/đích, nhập khóa OpenRouter và bấm **Dịch tài liệu**.
Khóa nhập trên giao diện chỉ dùng cho tác vụ hiện tại, không ghi vào cơ sở dữ
liệu hay cấu hình. Nội dung dịch được gửi tới dịch vụ đã cấu hình và có thể
phát sinh phí theo tài khoản của bạn. Chưa có khóa thì web vẫn mở được nhưng
không gửi tác vụ dịch được.

Để dùng khóa chung của máy chủ, sao chép `.env.example` thành `.env`, điền
`OPENROUTER_API_KEY`, rồi khởi động lại. DocWeave mặc định gọi OpenRouter tại
`https://openrouter.ai/api/v1` với model `openai/gpt-4o-mini`. Bạn có thể đổi
`OPENROUTER_BASE_URL` hoặc `DOCWEAVE_MODEL` sang bất kỳ model nào trên
[OpenRouter Models](https://openrouter.ai/models) tương thích Chat Completions.
Tên model cần dùng đúng dạng OpenRouter, ví dụ `google/gemini-2.0-flash-001`
hoặc `deepseek/deepseek-chat`. Không commit `.env`.

Lần dịch đầu tiên có thể chờ nạp thư viện và tải model/font qua Internet.
Giao diện vẫn hoạt động trong lúc đó. Dữ liệu mặc định nằm ở `.cache/docweave/`:
metadata SQLite, thư mục riêng cho từng tác vụ, và `runtime/` chứa model/font.
Kết quả và file đầu vào được dọn sau 24 giờ, kiểm tra mỗi phút khi máy chủ chạy.
Cache nội dung bản dịch của BabelDOC bị tắt; cache model/font được giữ để tái sử dụng.

### Phạm vi bản đầu

- PDF có văn bản chọn được; đầu vào mặc định tối đa 25 MB / 100 trang.
- Một tác vụ chạy, tối đa tám tác vụ chờ. Có hủy và giới hạn thời gian 30 phút.
- Lịch sử theo cookie của trình duyệt, không phải hệ thống tài khoản. Mất cookie
  thì không truy cập lại lịch sử bằng giao diện được.
- Trạng thái được lưu qua lần khởi động lại; tác vụ dang dở được báo gián đoạn,
  không tự dịch lại để tránh phát sinh phí ngoài ý muốn.
- Chỉ chạy một máy chủ cho một thư mục dữ liệu. Chưa có thanh toán hay phân quyền nhóm.

## Kiểm tra

```sh
uv run python -m unittest discover -s tests -v
uv run python scripts/check_core.py
```

Bộ unittest kiểm tra upload, kiểm tra PDF, tách phiên, tải file, hủy, timeout,
dọn file và phục hồi trạng thái bằng tiến trình xử lý giả lập.
`check_core.py` chạy **pipeline BabelDOC thật** với một dịch vụ phản hồi cố định
trên localhost, xuất và đọc lại hai PDF để kiểm tra tích hợp. Lần đầu cần tải
model/font; không dùng khóa thật, không đo chất lượng dịch AI. Kết quả kiểm tra
nằm ở `.cache/core-check/`. Để kiểm tra chất lượng thực tế, dịch PDF với dịch vụ thật.

## Đưa lên máy chủ

Xem [hướng dẫn triển khai](docs/DEPLOYMENT.md). Bản chạy trực tiếp mặc định chỉ
mở localhost. Khi mở ra mạng cần mã truy cập và cấu hình domain; dùng HTTPS
trước khi truyền khóa API hay tài liệu qua mạng.

## Cấu trúc dự án

DocWeave phát triển trên bản fork BabelDOC được lưu trực tiếp trong repo.

```text
src/docweave/          Mã nguồn mới của DocWeave
tests/                Kiểm thử của DocWeave
configs/              Cấu hình của DocWeave
scripts/              Script hỗ trợ phát triển
docs/                 Tài liệu của DocWeave
third_party/BabelDOC/  Mã nguồn, tài liệu, ví dụ và cấu hình BabelDOC gốc
```

## BabelDOC CLI

Dùng Python 3.10–3.13 và chạy từ thư mục gốc repo:

```sh
uv sync
uv run babeldoc --version
uv run babeldoc --help
uv run python -m unittest discover -s tests
```

Trên Windows PowerShell, nếu BabelDOC in lỗi `UnicodeEncodeError` khi log có
tiếng Trung, chạy qua script này:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/babeldoc.ps1 --help
```

Ngoài giao diện web, vẫn có thể dùng trực tiếp BabelDOC CLI. CLI của BabelDOC
vẫn nhận tham số tương thích OpenAI; để gọi OpenRouter, dùng:

```powershell
$env:OPENROUTER_API_KEY = "sk-or-v1-..."
powershell -ExecutionPolicy Bypass -File scripts/babeldoc.ps1 --files path/to/input.pdf --openai --openai-api-key $env:OPENROUTER_API_KEY --openai-base-url https://openrouter.ai/api/v1 --openai-model openai/gpt-4o-mini
```

`uv` cài cả DocWeave và BabelDOC cục bộ ở chế độ editable. Các import
`import babeldoc` và `from babeldoc...` giữ nguyên; không cần sửa `PYTHONPATH`.
Sau khi di chuyển repo, chạy lại `uv sync` để cập nhật đường dẫn cài đặt.

Nếu dùng pip, cài cả hai package trong cùng một lệnh, trong môi trường ảo:

```sh
python -m pip install -e ./third_party/BabelDOC -e .
babeldoc --help
```

Đường dẫn PDF, cấu hình và đầu ra tương đối được tính từ thư mục đang chạy.
Ví dụ PDF gốc hiện ở `third_party/BabelDOC/examples/ci/test.pdf`.

## Phát triển

Xem [hướng dẫn đóng góp](docs/CONTRIBUTING.md). Mã mới đặt trong `src/docweave/`;
chỉ sửa BabelDOC khi có nhu cầu cụ thể. Metadata và dependency của BabelDOC
được giữ tại `third_party/BabelDOC/pyproject.toml`.

README cấp gốc của BabelDOC đã được bỏ. Tài liệu kỹ thuật gốc vẫn ở
[third_party/BabelDOC/docs/](third_party/BabelDOC/docs/README.md).
Các workflow GitHub gốc được lưu trong `third_party/BabelDOC/.github/` để
tham khảo; GitHub không tự chạy workflow ở vị trí này.

Repo giữ nguyên [giấy phép AGPL-3.0](LICENSE) từ BabelDOC, cùng bản LICENSE
gốc trong `third_party/BabelDOC/` và các thông báo bản quyền đi kèm mã nguồn.
