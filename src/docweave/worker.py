"""Isolated BabelDOC adapter. Secrets arrive only through the environment."""

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path


def emit(kind, **data):
    print(
        "DOCWEAVE:" + json.dumps(dict(type=kind, **data), ensure_ascii=False),
        flush=True,
    )


STAGES = {
    "Parse PDF and Create Intermediate Representation": "Đang đọc nội dung PDF",
    "DetectScannedFile": "Đang kiểm tra loại tài liệu",
    "Parse Page Layout": "Đang phân tích bố cục",
    "Parse Paragraphs": "Đang nhận diện đoạn văn",
    "Translate Paragraphs": "Đang dịch nội dung",
    "Typesetting": "Đang dàn trang bản dịch",
    "Save PDF": "Đang xuất PDF",
    "Parse Formulas and Styles": "Đang nhận diện công thức và định dạng",
    "Add Fonts": "Đang nhúng font vào tài liệu",
    "Generate drawing instructions": "Đang dựng trang PDF",
    "Subset font": "Đang tối ưu font",
    "Parse Table": "Đang nhận diện bảng",
}


def run(folder):
    emit("progress", stage="Đang nạp thư viện xử lý PDF", progress=0)
    from babeldoc.docvision.base_doclayout import DocLayoutModel
    from babeldoc.format.pdf.high_level import async_translate, init
    from babeldoc.format.pdf.translation_config import (
        TranslationConfig,
        WatermarkOutputMode,
    )
    from babeldoc.translator.translator import (
        OpenAITranslator,
        set_translate_rate_limiter,
    )

    options = json.loads((folder / "options.json").read_text(encoding="utf-8"))
    init()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("missing_api_key")
    translator = OpenAITranslator(
        options["lang_in"],
        options["lang_out"],
        model=os.environ.get("DOCWEAVE_MODEL", "openai/gpt-4o-mini"),
        base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=api_key,
        ignore_cache=True,
    )
    # Fail quickly on invalid credentials before downloading or processing assets.
    emit("progress", stage="Đang kiểm tra kết nối dịch vụ dịch", progress=0)
    translator.client.with_options(timeout=20, max_retries=0).chat.completions.create(
        model=translator.model,
        messages=[{"role": "user", "content": "Reply OK."}],
        max_tokens=8,
    )
    emit(
        "progress",
        stage="Đang chuẩn bị model và font (lần đầu có thể cần tải xuống)",
        progress=0,
    )
    model = DocLayoutModel.load_onnx()
    set_translate_rate_limiter(2)
    config = TranslationConfig(
        translator=translator,
        input_file=folder / "input.pdf",
        lang_in=options["lang_in"],
        lang_out=options["lang_out"],
        doc_layout_model=model,
        output_dir=folder / "output",
        working_dir=folder / "work",
        qps=2,
        pool_max_workers=2,
        auto_extract_glossary=False,
        report_interval=0.5,
        watermark_output_mode=WatermarkOutputMode.NoWatermark,
    )

    async def translate():
        finished = False
        async for event in async_translate(config):
            if event["type"].startswith("progress_"):
                stage = event.get("stage", "")
                emit(
                    "progress",
                    stage=STAGES.get(stage, "Đang xử lý tài liệu: " + stage),
                    progress=event.get("overall_progress", 0),
                )
            elif event["type"] == "error":
                error = event.get("error")
                if isinstance(error, Exception):
                    raise error
                raise RuntimeError("translation_failed")
            elif event["type"] == "finish":
                result = event["translate_result"]
                if not result.mono_pdf_path or not result.dual_pdf_path:
                    raise RuntimeError("missing_output")
                shutil.copyfile(result.mono_pdf_path, folder / "translated.pdf")
                shutil.copyfile(result.dual_pdf_path, folder / "bilingual.pdf")
                finished = True
                break  # BabelDOC's callback stream remains open after its finish event.
        if not finished:
            raise RuntimeError("missing_output")

    try:
        asyncio.run(translate())
    finally:
        translator.client.close()


def main():
    try:
        run(Path(sys.argv[1]).resolve())
    except Exception as exc:
        name = type(exc).__name__
        if name in ("AuthenticationError", "PermissionDeniedError"):
            message = (
                "Khóa API không hợp lệ hoặc không có quyền sử dụng model đã cấu hình."
            )
        elif name == "RateLimitError":
            message = "Dịch vụ dịch đã hết hạn mức hoặc đang giới hạn yêu cầu. Kiểm tra tài khoản rồi thử lại."
        elif name in (
            "APIConnectionError",
            "APITimeoutError",
            "ConnectError",
            "ReadTimeout",
        ):
            message = (
                "Không kết nối được dịch vụ dịch. Kiểm tra mạng và địa chỉ dịch vụ."
            )
        elif name in ("NotFoundError", "BadRequestError"):
            message = "Model hoặc cấu hình OpenRouter chưa phù hợp. Kiểm tra DOCWEAVE_MODEL và OPENROUTER_BASE_URL."
        else:
            message = "Không xử lý được PDF này. Hãy thử PDF có văn bản chọn được, kiểm tra model/font và cấu hình dịch vụ."
        emit("error", message=message)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
