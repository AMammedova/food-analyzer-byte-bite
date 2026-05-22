# Contribution Statement

**Team:** Byte Bite  
**Topic:** Topic 2 — AI Food Analyzer  
**Repository:** [https://github.com/AMammedova/food-analyzer-byte-bite](https://github.com/AMammedova/food-analyzer-byte-bite)  
**Final tag:** `v1.0-final`  
**Submission date:** 2026-05-23

---

## Member A — Aysel Mamedova (`@AMammedova`)

**Owned:**
- `src/foodanalyzer/config.py` — pydantic-settings typed configuration layer
- `src/foodanalyzer/models.py` — SE-layer Pydantic data models (`IngredientOut`, `TotalsOut`, `AnalysisResult`, `AnalysisRecord`)
- `src/foodanalyzer/validation.py` — magic-byte image format check, configurable size limit
- `src/foodanalyzer/cli.py` — full CLI: `python -m foodanalyzer analyze <path> [--offline] [--json]`
- `src/foodanalyzer/static/index.html` — single-page web UI (drag-and-drop upload, results table, history)
- `Dockerfile` — production image (`python:3.12-slim`, non-root user, `uvicorn` CMD)
- `docker-compose.yml` — PostgreSQL + pgAdmin dev stack with health checks
- `.env.example`, `.gitignore`, `pytest.ini`, `README.md`
- Project setup: GitHub repository, branch protection rules, PR template
- Branches: `aysel/infra-config-docker`, `aysel/models-core-cli`, `aysel/logging-validation`, `aysel/demo-ui-v2`, `aysel/final-polish`

**Co-owned (paired or substantially edited):**
- `src/foodanalyzer/api.py` — integrated web UI (`GET /`), added `load_dotenv` env-loading fix
- `ai/providers/google.py` — fixed Gemini SDK 0.3.0 incompatibility (`types.Part.from_bytes`)
- `requirements.txt` — dependency pinning and additions (`python-dotenv`, `aiofiles`, `python-multipart`)

**Reviewed (PRs reviewed and merged):**
- All six PRs from Gülnur, PR from Şəmistan, storage PRs from Rəhimə

**Approximate share of commits:** ~25%

---

## Member B — Gülnur Məmmədova (`@gulnurmammadova`)

**Owned:**
- `src/foodanalyzer/services/ai_service.py` — AIService wrapper: `tenacity` retry (4 attempts, exponential backoff) + 60 s `asyncio` timeout around VLM calls
- `src/foodanalyzer/services/retry.py` — reusable `AsyncRetrying` policy shared across services
- `src/foodanalyzer/services/nutrition_cache.py` — coroutine-safe in-memory TTL cache with `asyncio.Lock`
- `src/foodanalyzer/concurrency/pipeline.py` — `NutritionPipeline`: `asyncio.gather` + `Semaphore(MAX_PARALLEL)` fan-out, graceful partial-failure handling
- `tests/test_services.py` — unit tests for AIService (retry paths, timeout) and NutritionCache (TTL, lock)
- `tests/test_concurrency.py` — concurrency tests: one-task-fails others-complete, semaphore bound
- `artefacts/` — benchmark results, full coverage report, sample API output
- Branches: `gulnur/ai-service-retry`, `gulnur/nutrition-cache`, `gulnur/nutrition-pipeline`, `gulnur/test-services`, `gulnur/test-pipeline`, `gulnur/project-artifacts`

**Co-owned:**
- `src/foodanalyzer/core/analyzer.py` — wired `AIService` and `NutritionPipeline` into the central analysis pipeline

**Reviewed:**
- PRs from Aysel and Rəhimə

**Approximate share of commits:** ~25%

---

## Member C — Şəmistan Hüseynov (`@Shamistanh`)

**Owned:**
- `src/foodanalyzer/api.py` — FastAPI application: `POST /analyze`, `GET /history` (pagination), `GET /health`, lifespan pool management, request/response serialisation
- `tests/test_api.py` — API endpoint tests: happy path end-to-end, error paths (invalid image, oversized file, missing DB), pagination correctness
- `tests/test_analyzer.py` — integration tests for the `FoodAnalyzer` orchestration layer
- Branch: `api-endpoints`

**Co-owned:**
- `src/foodanalyzer/core/analyzer.py` — endpoint wiring, `AnalysisResult` response structure, error propagation
- `src/foodanalyzer/models.py` — `AnalysisResult` / `AnalysisRecord` field definitions (with Aysel)

**Reviewed:**
- PRs from Gülnur (`gulnur/nutrition-pipeline`, `gulnur/test-pipeline`)

**Approximate share of commits:** ~25%

---

## Member D — Rəhimə Kərimova (`@RahimaKarimova`)

**Owned:**
- `src/foodanalyzer/storage/db.py` — `asyncpg` connection pool creation, `init_schema()`, `create_pool` / `close_pool` lifespan helpers
- `src/foodanalyzer/storage/repository.py` — SQL CRUD: `save(AnalysisRecord)` with `RETURNING`, `list_recent(limit, offset)` with pagination
- `src/foodanalyzer/logging_config.py` — `StructuredFormatter`: human-readable text + `key=value` extras; JSON mode via `LOG_FORMAT=json`
- `src/foodanalyzer/core/analyzer.py` — main `FoodAnalyzer` class: full pipeline orchestration (validate → VLM → nutrition → totals → persist)
- `tests/test_db.py` — pool lifecycle and schema initialisation tests
- `tests/test_repository.py` — CRUD tests with mocked `asyncpg` connection
- `tests/test_logging_config.py` — structured log output and JSON mode tests
- Branches: `rahima/storage-pool`, `rahima/storage-repository`, `rahima/structured-logging`, `rahima/wire-analyzer-services`, `rahima/api-contract-proposal`, `rahima/fix-typing-self-py310`

**Co-owned:**
- `src/foodanalyzer/models.py` — `AnalysisRecord` schema (with Aysel)

**Reviewed:**
- PRs from Şəmistan (`semistan/api-endpoints`)

**Approximate share of commits:** ~25%

---

## Signatures

By signing below, we affirm that:
- The contributions described above are accurate.
- The commit percentages reflect actual work, not artificially split commits.
- Every line of code in the repository can be defended by at least one team member.

| Member | Signature | Date |
|---|---|---|
| Aysel Mamedova | __________________________ | 2026-05-23 |
| Gülnur Məmmədova | __________________________ | 2026-05-23 |
| Şəmistan Hüseynov | __________________________ | 2026-05-23 |
| Rəhimə Kərimova | __________________________ | 2026-05-23 |
