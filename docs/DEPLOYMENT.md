# Triển khai DocWeave

## Chạy trực tiếp

```sh
uv sync --locked
uv run docweave --port 8000
```

Trang web tại http://127.0.0.1:8000. Cấu hình qua `.env`, mẫu ở `.env.example`.
Khởi động lại sau khi đổi cấu hình. Cần kết nối tới dịch vụ dịch, nguồn tải
model/font của BabelDOC và đủ dung lượng để lưu PDF cùng file trung gian.
Thời gian và RAM phụ thuộc tài liệu; đo trên tập PDF thực tế trước khi tăng giới hạn.

## Docker trên máy chủ

1. Sao chép `.env.example` thành `.env`.
2. Đặt `DOCWEAVE_ACCESS_TOKEN` thành chuỗi ngẫu nhiên dài, `OPENROUTER_API_KEY`
   bằng khóa lấy từ [OpenRouter Keys](https://openrouter.ai/keys), và chọn model
   trong `DOCWEAVE_MODEL` nếu không dùng mặc định.
3. Thêm domain thật vào `DOCWEAVE_ALLOWED_HOSTS`, giữ `127.0.0.1` để healthcheck hoạt động.
4. Chạy `docker compose up -d --build`.
5. Đặt reverse proxy HTTPS tới `127.0.0.1:8000`; giữ đúng Host, chuyển
   `X-Forwarded-Proto`, giới hạn request khoảng 26 MB cho mức tải lên mặc định 25 MB.
   Chỉ tin proxy do bạn kiểm soát. Không mở trực tiếp cổng HTTP ra Internet.

OpenRouter tính phí theo model và tài khoản của bạn. DocWeave không lưu khóa
trong lịch sử tác vụ; khóa nhập trên trang chỉ được truyền cho subprocess dịch.

Compose chỉ bind localhost, tự khởi động lại và giữ dữ liệu trong volume
`docweave-data`. Container chạy bằng người dùng không có quyền root.
`docker compose logs -f` để xem log máy chủ; không ghi khóa API vào log.
Container không chứa `.env` hay dữ liệu kiểm thử từ máy phát triển.

Nếu không dùng Docker, chạy dưới trình quản lý dịch vụ của hệ điều hành.
Khi bind IP ngoài localhost, `uv run docweave --host 0.0.0.0` yêu cầu
`DOCWEAVE_ACCESS_TOKEN`. Chỉ chạy **một process / một thư mục dữ liệu**, không thêm
`--workers` hay `--reload`; khóa file ngăn hai hàng đợi cùng sử dụng dữ liệu.

## Vận hành

- `GET /api/health`: kiểm tra web đang sống; không khẳng định API dịch hoặc model đã sẵn sàng.
- `GET /api/config`: cấu hình công khai, không trả khóa API; yêu cầu mã truy cập nếu được bật.
- Khi bật mã truy cập, các API khác cần `Authorization: Bearer …`. Trình duyệt
  hỏi mã khi mở trang và chỉ giữ trong bộ nhớ đến khi tải lại.
- Phiên được tách bằng cookie HttpOnly/SameSite. Đây là bản thử nghiệm có kiểm
  soát truy cập chung, chưa thay thế hệ thống tài khoản cho SaaS nhiều khách hàng.
- Mỗi tác vụ chạy ở subprocess riêng, được kết thúc khi hủy hoặc hết thời gian.
  Khi máy chủ khởi động lại, tác vụ đang chờ/chạy báo lỗi gián đoạn để gửi lại.
- Mặc định dọn file sau 24 giờ tính từ khi tạo; tác vụ đang xử lý không bị dọn.
  Việc xóa diễn ra khi máy chủ chạy; không bảo đảm xóa vật lý khỏi backup/ổ đĩa.
- Cache model/font tồn tại trong `runtime/`; không lưu cache nội dung dịch giữa
  các tác vụ. PDF và dữ liệu trung gian cần được bảo vệ như tài liệu gốc.
- Bộ xử lý không ghi lỗi thô từ nhà cung cấp vào lịch sử để tránh lộ khóa hoặc
  nội dung tài liệu. Giao diện trả hướng dẫn lỗi an toàn; dùng PDF mẫu không nhạy
  cảm qua CLI nếu cần chẩn đoán sâu.

Trước khi phục vụ công khai ở quy mô lớn, cần tài khoản/hạn mức theo người dùng,
giới hạn tần suất ở proxy, giám sát dung lượng/tài nguyên và kiểm thử tải thực tế.
Dockerfile là phương án triển khai Python/ONNX, không phải bản chạy trên Cloudflare Workers.

## Trạng thái xác minh

Đã kiểm tra trên Windows/Python 3.12: khởi động web, API/tệp giao diện, 10 bài
unittest và pipeline BabelDOC thật xuất hai PDF có văn bản tiếng Việt với API
fixture cục bộ. Chưa kiểm tra chất lượng qua nhà cung cấp dịch thật do chưa có
khóa API. Dockerfile/Compose đã được chuẩn bị nhưng chưa chạy container trên
máy phát triển vì Docker Engine chưa hoạt động.
