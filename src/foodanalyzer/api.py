"""FastAPI HTTP API — POST /analyze, GET /health, GET /history, GET /."""

from __future__ import annotations

import logging
from pathlib import Path as _Path

# Load .env into os.environ so that ai/ provider modules (which use os.getenv
# directly) pick up LLM_PROVIDER, GOOGLE_API_KEY, etc. without needing the
# variables to be exported in the shell before running uvicorn.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(_Path(__file__).parents[2] / ".env", override=False)
except ImportError:
    pass
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ai.providers.base import ProviderError
from foodanalyzer.config import get_settings
from foodanalyzer.core.analyzer import analyze
from foodanalyzer.logging_config import setup_logging
from foodanalyzer.models import AnalysisRecord, AnalysisResult
from foodanalyzer.storage import db, repository
from foodanalyzer.validation import ValidationError, validate_image_bytes

_STATIC_DIR = Path(__file__).parent / "static"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open DB pool on startup; close on shutdown."""
    settings = get_settings()
    pool = await db.create_pool(settings)
    await db.init_schema(pool)
    app.state.pool = pool
    logger.info("Database pool ready")
    try:
        yield
    finally:
        await db.close_pool(pool)
        logger.info("Database pool closed")


def create_app(*, lifespan_handler=lifespan) -> FastAPI:
    """Build the FastAPI application (lifespan overridable in tests)."""
    settings = get_settings()
    setup_logging(level=settings.log_level)

    app = FastAPI(title="Food Analyzer", lifespan=lifespan_handler)
    app.state.vlm = None
    app.state.nutrition = None

    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def ui() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    @app.exception_handler(ValidationError)
    async def validation_error_handler(
        _request: Request, exc: ValidationError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(ProviderError)
    async def provider_error_handler(
        _request: Request, exc: ProviderError
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/history")
    async def history(
        request: Request,
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        rows = await _list_recent(request, limit=limit + 1, offset=offset)  # +1 for has_more probe
        has_more = len(rows) > limit
        items = rows[:limit]
        return {
            "items": [_record_json(r) for r in items],
            "page": {
                "limit": limit,
                "offset": offset,
                "returned": len(items),
                "has_more": has_more,
            },
        }

    @app.post("/analyze", response_model=AnalysisResult)
    async def analyze_upload(
        request: Request, file: UploadFile = File(...)
    ) -> AnalysisResult:
        settings = get_settings()
        filename = file.filename or "upload.jpg"
        content = await file.read()

        validate_image_bytes(content, filename, settings.max_image_size_bytes)

        upload_dir = Path(settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / f"{uuid.uuid4().hex}_{Path(filename).name}"
        dest.write_bytes(content)

        vlm = request.app.state.vlm
        nutrition = request.app.state.nutrition

        try:
            result = await analyze(dest, vlm=vlm, nutrition=nutrition)
        except Exception:
            dest.unlink(missing_ok=True)
            raise

        try:
            await _save_result(request, result)
        except Exception as exc:
            logger.warning("Failed to persist analysis history: %s", exc)

        return result

    return app


app = create_app()


async def _list_recent(
    request: Request, *, limit: int, offset: int = 0
) -> list[AnalysisRecord]:
    if history_repo := getattr(request.app.state, "history_repo", None):
        return await history_repo.list_recent(limit=limit, offset=offset)
    pool = request.app.state.pool
    return await repository.list_recent(pool, limit=limit, offset=offset)


async def _save_result(request: Request, result: AnalysisResult) -> AnalysisRecord:
    record = AnalysisRecord.from_result(result)
    if history_repo := getattr(request.app.state, "history_repo", None):
        return await history_repo.save(record)
    pool = request.app.state.pool
    return await repository.save(pool, record)


def _record_json(record: AnalysisRecord) -> dict[str, Any]:
    return record.model_dump(mode="json")
