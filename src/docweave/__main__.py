import argparse
import os
import sys

from dotenv import load_dotenv


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    load_dotenv()
    parser = argparse.ArgumentParser(description="DocWeave — dịch PDF trên trình duyệt")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost", "::1") and not os.getenv(
        "DOCWEAVE_ACCESS_TOKEN"
    ):
        parser.error("Cần đặt DOCWEAVE_ACCESS_TOKEN trước khi mở máy chủ ra mạng.")
    import uvicorn

    uvicorn.run(
        "docweave.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        workers=1,
    )


if __name__ == "__main__":
    main()
