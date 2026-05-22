# Food Analyzer — Byte Bite (production image)
# Build:  docker build -t food-analyzer .
# Run:    docker run -p 8000:8000 --env-file .env food-analyzer
# Stack:  docker compose -f docker-compose.prod.yml up -d --build

FROM python:3.12-slim

LABEL org.opencontainers.image.title="Food Analyzer — Byte Bite"
LABEL org.opencontainers.image.source="https://github.com/AMammedova/food-analyzer-byte-bite"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app:/app/src

WORKDIR /app

# Install dependencies first (better layer cache on code changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code (ai module + SE layer + static UI)
COPY ai/ ./ai/
COPY src/ ./src/
COPY data/ ./data/
COPY uploads/ ./uploads/

RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "foodanalyzer.api:app", "--host", "0.0.0.0", "--port", "8000"]
