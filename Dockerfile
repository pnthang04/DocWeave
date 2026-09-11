FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONUTF8=1 \
    DOCWEAVE_DATA_DIR=/app/data
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 libfreetype6 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.12.9
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY third_party/BabelDOC ./third_party/BabelDOC
RUN uv sync --locked --no-dev \
    && useradd --create-home --uid 10001 docweave \
    && mkdir /app/data && chown docweave:docweave /app/data
USER docweave
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]
CMD ["/app/.venv/bin/python", "-m", "docweave", "--host", "0.0.0.0", "--port", "8000"]
