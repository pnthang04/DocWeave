"""Run the real BabelDOC pipeline against a LOCAL deterministic API fixture.

This verifies integration and PDF generation, not AI translation quality.
First run downloads BabelDOC model/font assets. No paid API or real key is used.
Run from the repository root: uv run python scripts/check_core.py
"""

import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pymupdf

TRANSLATION = (
    "Đây là tài liệu kiểm thử. Bản dịch tiếng Việt giúp bạn đọc và đối chiếu nội dung."
)


class Fixture(BaseHTTPRequestHandler):
    calls = 0

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = body["messages"][-1]["content"]
        content = TRANSLATION
        if prompt == "Reply OK.":
            content = "OK"
        else:
            Fixture.calls += 1
            ids = re.findall(r'"id"\s*:\s*(\d+)', prompt)
            if ids:
                content = json.dumps(
                    [{"id": int(i), "output": TRANSLATION} for i in dict.fromkeys(ids)],
                    ensure_ascii=False,
                )
        result = json.dumps(
            {
                "id": "local-fixture",
                "object": "chat.completion",
                "created": 0,
                "model": "fixture",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 30,
                    "completion_tokens": 30,
                    "total_tokens": 60,
                },
            },
            ensure_ascii=False,
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(result)))
        self.end_headers()
        self.wfile.write(result)

    def log_message(self, *args):
        pass


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    root = Path(".cache/core-check").resolve()
    root.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_textbox(
            (72, 90, 510, 250),
            "This is an integration test document. The translated document helps readers understand and compare information across languages.",
            fontsize=14,
        )
        pdf.save(root / "input.pdf")
    (root / "options.json").write_text(
        json.dumps({"lang_in": "en", "lang_out": "vi"}), encoding="utf-8"
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = os.environ.copy()
    env.update(
        OPENROUTER_API_KEY="local-fixture-only",
        OPENROUTER_BASE_URL=f"http://127.0.0.1:{server.server_port}/v1",
        DOCWEAVE_MODEL="fixture",
        BABELDOC_CACHE_DIR=str(Path(".cache/docweave/runtime").resolve()),
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
    )
    try:
        result = subprocess.run(
            [sys.executable, "-m", "docweave.worker", str(root)], env=env, timeout=900
        )
        assert result.returncode == 0, "Core worker failed"
        assert Fixture.calls > 0, "No translation request reached the fixture"
        for name in ("translated.pdf", "bilingual.pdf"):
            with pymupdf.open(root / name) as pdf:
                text = "".join(page.get_text() for page in pdf)
                assert len(pdf) > 0 and "kiểm thử" in text, (name, text)
                print(
                    f"OK: {name}, {len(pdf)} page(s), Vietnamese text verified",
                    flush=True,
                )
        print(
            "Real BabelDOC pipeline passed with a local API fixture. No live-provider quality check.",
            flush=True,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    main()
