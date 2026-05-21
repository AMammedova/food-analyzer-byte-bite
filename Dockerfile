FROM python:3.12-slim

LABEL org.opencontainers.image.title="Food Analyzer — Byte Bite"
LABEL org.opencontainers.image.source="https://github.com/AMammedova/food-analyzer-byte-bite"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app:/app/src

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/uploads \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "foodanalyzer.api:app", "--host", "0.0.0.0", "--port", "8000"]
