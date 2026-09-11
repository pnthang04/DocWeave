"""DocWeave web application; heavyweight PDF imports stay outside startup."""

import hashlib
import hmac
import os
import queue
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from docweave.jobs import Jobs

LANGUAGES = {
    "en": "Tiếng Anh",
    "vi": "Tiếng Việt",
    "zh": "Tiếng Trung",
    "ja": "Tiếng Nhật",
    "ko": "Tiếng Hàn",
    "fr": "Tiếng Pháp",
    "de": "Tiếng Đức",
    "es": "Tiếng Tây Ban Nha",
}
STATIC = Path(__file__).parent / "static"


class BodyLimit:
    def __init__(self, app, limit):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        size = 0

        async def limited_receive():
            nonlocal size
            message = await receive()
            size += len(message.get("body", b""))
            if size > self.limit:
                raise HTTPException(413, "Tệp tải lên vượt dung lượng cho phép.")
            return message

        await self.app(scope, limited_receive, send)


def create_app(data_dir=None):
    load_dotenv()
    root = Path(data_dir or os.getenv("DOCWEAVE_DATA_DIR", ".cache/docweave"))
    max_mb = int(os.getenv("DOCWEAVE_MAX_UPLOAD_MB", "25"))
    max_pages = int(os.getenv("DOCWEAVE_MAX_PAGES", "100"))
    token = os.getenv("DOCWEAVE_ACCESS_TOKEN", "")

    @asynccontextmanager
    async def lifespan(app):
        app.state.jobs = Jobs(
            root,
            timeout=int(os.getenv("DOCWEAVE_JOB_TIMEOUT", "1800")),
            retention=int(os.getenv("DOCWEAVE_RETENTION_HOURS", "24")) * 3600,
        )
        yield
        await run_in_threadpool(app.state.jobs.close)

    app = FastAPI(
        title="DocWeave",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    hosts = [
        h.strip()
        for h in os.getenv("DOCWEAVE_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(
            ","
        )
        if h.strip()
    ]
    app.add_middleware(BodyLimit, limit=max_mb * 1024 * 1024 + 65536)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    @app.middleware("http")
    async def guard(request, call_next):
        if request.url.path.startswith("/api/"):
            if (
                request.url.path != "/api/health"
                and token
                and not hmac.compare_digest(
                    request.headers.get("authorization", "").encode(),
                    ("Bearer " + token).encode(),
                )
            ):
                return JSONResponse(
                    {"detail": "Nhập mã truy cập để sử dụng máy chủ này."},
                    status_code=401,
                )
            if request.method not in ("GET", "HEAD"):
                origin = request.headers.get("origin")
                if request.headers.get("x-docweave") != "1" or (
                    origin and urlsplit(origin).netloc != request.headers.get("host")
                ):
                    return JSONResponse(
                        {"detail": "Yêu cầu không hợp lệ."}, status_code=403
                    )
            raw_size = request.headers.get("content-length", "0")
            if not raw_size.isdigit() or int(raw_size) > max_mb * 1024 * 1024 + 65536:
                return JSONResponse(
                    {"detail": f"Tệp tối đa {max_mb} MB."}, status_code=413
                )
        owner = request.cookies.get("docweave_session", "")
        new_owner = not re.fullmatch(r"[a-f0-9]{64}", owner)
        if new_owner:
            owner = secrets.token_hex(32)
        request.state.owner = hashlib.sha256(owner.encode()).hexdigest()
        response = await call_next(request)
        if new_owner:
            response.set_cookie(
                "docweave_session",
                owner,
                httponly=True,
                samesite="strict",
                secure=request.url.scheme == "https",
                max_age=30 * 86400,
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "auth_required": bool(token)}

    @app.get("/api/config")
    def config():
        return dict(
            server_key=bool(os.getenv("OPENROUTER_API_KEY")),
            model=os.getenv("DOCWEAVE_MODEL", "openai/gpt-4o-mini"),
            max_upload_mb=max_mb,
            max_pages=max_pages,
            languages=LANGUAGES,
            retention_hours=int(os.getenv("DOCWEAVE_RETENTION_HOURS", "24")),
        )

    @app.get("/api/jobs")
    def list_jobs(request: Request):
        return request.app.state.jobs.list(request.state.owner)

    def owned(request, job_id):
        job = request.app.state.jobs.get(job_id, request.state.owner)
        if not job:
            raise HTTPException(404, "Không tìm thấy tác vụ hoặc tác vụ đã hết hạn.")
        return job

    @app.get("/api/jobs/{job_id}")
    def get_job(request: Request, job_id: str):
        return owned(request, job_id)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(request: Request, job_id: str):
        owned(request, job_id)
        request.app.state.jobs.cancel(job_id)
        return owned(request, job_id)

    @app.get("/api/jobs/{job_id}/download/{kind}")
    def download(request: Request, job_id: str, kind: str):
        job = owned(request, job_id)
        if job["status"] != "done" or kind not in ("translated", "bilingual"):
            raise HTTPException(404, "Kết quả chưa sẵn sàng.")
        path = request.app.state.jobs.root / job_id / (kind + ".pdf")
        if not path.is_file():
            raise HTTPException(404, "Tệp kết quả không còn trên máy chủ.")
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=Path(job["filename"]).stem + "-" + kind + ".pdf",
        )

    @app.post("/api/jobs", status_code=202)
    async def submit(request: Request):
        async with request.form(max_files=1, max_fields=4, max_part_size=8192) as form:
            upload = form.get("file")
            if not upload or not hasattr(upload, "read"):
                raise HTTPException(400, "Hãy chọn một tệp PDF.")
            lang_in, lang_out = form.get("lang_in", "en"), form.get("lang_out", "vi")
            if (
                not isinstance(lang_in, str)
                or not isinstance(lang_out, str)
                or lang_in not in LANGUAGES
                or lang_out not in LANGUAGES
                or lang_in == lang_out
            ):
                raise HTTPException(400, "Chọn hai ngôn ngữ khác nhau trong danh sách.")
            key = form.get("api_key", "")
            if not isinstance(key, str) or len(key) > 4096:
                raise HTTPException(400, "Khóa API không hợp lệ.")
            key = (
                key.strip()
                or os.getenv("OPENROUTER_API_KEY", "")
            )
            if not key:
                raise HTTPException(
                    400,
                    "Nhập khóa OpenRouter hoặc cấu hình OPENROUTER_API_KEY trên máy chủ để dịch.",
                )
            content = await upload.read(max_mb * 1024 * 1024 + 1)
            if len(content) > max_mb * 1024 * 1024:
                raise HTTPException(413, f"Tệp tối đa {max_mb} MB.")
            if not content.startswith(b"%PDF-"):
                raise HTTPException(400, "Tệp không phải PDF hợp lệ.")

            def validate():
                import pymupdf

                try:
                    with pymupdf.open(stream=content, filetype="pdf") as pdf:
                        if pdf.needs_pass:
                            raise HTTPException(
                                400, "Hãy gỡ mật khẩu PDF trước khi tải lên."
                            )
                        if not 1 <= len(pdf) <= max_pages:
                            raise HTTPException(
                                400, f"PDF cần có từ 1 đến {max_pages} trang."
                            )
                        return len(pdf)
                except HTTPException:
                    raise
                except Exception:
                    raise HTTPException(
                        400, "Không đọc được PDF. Tệp có thể đã hỏng."
                    ) from None

            pages = await run_in_threadpool(validate)
            filename = (
                re.sub(
                    r"[\x00-\x1f\x7f]",
                    "",
                    (upload.filename or "document.pdf")
                    .replace("\\", "/")
                    .split("/")[-1],
                )[:150]
                or "document.pdf"
            )
            try:
                return request.app.state.jobs.submit(
                    request.state.owner,
                    filename,
                    content,
                    pages,
                    dict(lang_in=lang_in, lang_out=lang_out),
                    {"OPENROUTER_API_KEY": key},
                )
            except queue.Full:
                raise HTTPException(
                    429, "Hàng đợi đang đầy. Vui lòng chờ một tác vụ hoàn tất."
                ) from None

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
