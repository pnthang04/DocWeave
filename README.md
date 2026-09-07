# DocWeave

DocWeave phát triển trên bản fork BabelDOC được lưu trực tiếp trong repo.

```text
src/docweave/          Mã nguồn mới của DocWeave
tests/                Kiểm thử của DocWeave
configs/              Cấu hình của DocWeave
scripts/              Script hỗ trợ phát triển
docs/                 Tài liệu của DocWeave
third_party/BabelDOC/  Mã nguồn, tài liệu, ví dụ và cấu hình BabelDOC gốc
```

## Cài đặt và chạy

Dùng Python 3.10–3.13 và chạy từ thư mục gốc repo:

```sh
uv sync
uv run babeldoc --version
uv run babeldoc --help
uv run python -m unittest discover -s tests
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
