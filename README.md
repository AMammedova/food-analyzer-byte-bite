# Food Analyzer — Byte Bite

> Upload a meal photo → AI identifies ingredients with portion sizes → USDA nutrition lookup → calories and macronutrient totals.

**Team:** Byte Bite  
**Topic:** 2 — AI Food Analyzer  
**Course:** AI-ENG-110 Software Engineering, AI Academy  
**Repository:** https://github.com/AMammedova/food-analyzer-byte-bite  
**Due:** May 23, 2026 at 23:59 (UTC+4)

---

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/AMammedova/food-analyzer-byte-bite.git
cd food-analyzer-byte-bite

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your API keys:

```env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash
GOOGLE_API_KEY=<your-google-api-key>

NUTRITION_PROVIDER=usda
USDA_API_KEY=<your-usda-api-key>

POSTGRES_USER=postgres
POSTGRES_PASSWORD=dev
POSTGRES_DB=foodanalyzer
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

> Get a free USDA key at https://fdc.nal.usda.gov/api-key-signup  
> **Never commit `.env`** — it is in `.gitignore`.

### 3. Start the database

```bash
docker compose up -d        # starts PostgreSQL + pgAdmin
docker compose ps           # db should show "healthy"
```

### 4. Run the API server

```bash
# Windows PowerShell
$env:PYTHONPATH="src"
uvicorn foodanalyzer.api:app --reload --port 8000

# macOS / Linux
PYTHONPATH=src uvicorn foodanalyzer.api:app --reload --port 8000
```

Open **http://localhost:8000** — the web UI loads automatically.

### 5. Try the CLI (offline, no API keys needed)

```bash
python data/_make_samples.py    # one-time: generate sample PNG images

$env:PYTHONPATH="src"           # Windows
python -m foodanalyzer analyze data/rice_chicken_broccoli.png --offline
```

---

## API usage

### Health check

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### Analyze a meal photo

```bash
curl -X POST http://localhost:8000/analyze \
     -F "file=@data/rice_chicken_broccoli.png"
```

Response:

```json
{
  "meal_recognized": true,
  "image_path": "uploads/abc123_rice_chicken_broccoli.png",
  "ingredients": [
    {"name": "white rice (cooked)", "estimated_grams": 180, "confidence": 0.95,
     "kcal": 234, "protein_g": 4.9, "carbs_g": 50.4, "fat_g": 0.5},
    {"name": "grilled chicken breast", "estimated_grams": 150, "confidence": 0.9,
     "kcal": 248, "protein_g": 46.5, "carbs_g": 0.0, "fat_g": 5.4}
  ],
  "totals": {"kcal": 509, "protein_g": 53.6, "carbs_g": 56.0, "fat_g": 6.3}
}
```

### Analysis history

```bash
curl "http://localhost:8000/history?limit=10&offset=0"
```

Response includes pagination:

```json
{
  "items": [ ... ],
  "page": {"limit": 10, "offset": 0, "returned": 3, "has_more": false}
}
```

---

## Run tests

```bash
$env:PYTHONPATH="src"           # Windows
pytest                          # all 158 tests
pytest --cov=foodanalyzer --cov-report=term-missing   # with coverage
pytest tests/test_ai_smoke.py -v                      # smoke tests only
```

All tests run **offline** — no API keys or network required.

---

## Docker

### Build and run the full application image

```bash
docker build -t food-analyzer .

docker run -p 8000:8000 \
  --env-file .env \
  food-analyzer
```

Open http://localhost:8000

### Local dev stack (PostgreSQL + pgAdmin only)

```bash
docker compose up -d     # start
docker compose ps        # verify healthy
docker compose down      # stop (data preserved)
docker compose down -v   # stop and delete all data
```

### pgAdmin

| URL | http://localhost:5051 |
|-----|-----------------------|
| Email | `admin@bytebite.local` |
| Password | `admin` |

The **Food Analyzer (Byte Bite)** server is pre-configured — no manual setup needed.

---

## Project layout

```
food-analyzer-byte-bite/
├── ai/                         # provided AI module — do not edit
│   ├── providers/              # Anthropic, OpenAI, Gemini adapters
│   ├── vlm.py                  # identify_ingredients()
│   ├── nutrition.py            # NutritionProvider / USDAProvider
│   └── schemas.py              # Ingredient, NutritionFacts
│
├── src/foodanalyzer/           # SE layer (our work)
│   ├── config.py               # pydantic-settings typed config
│   ├── models.py               # IngredientOut, AnalysisResult, AnalysisRecord
│   ├── validation.py           # image format + size checks
│   ├── logging_config.py       # structured logging (text / JSON)
│   ├── cli.py                  # python -m foodanalyzer analyze <path>
│   ├── api.py                  # FastAPI: POST /analyze, GET /history
│   ├── core/analyzer.py        # main pipeline (validate→VLM→nutrition→totals)
│   ├── services/               # AIService (retry+timeout), NutritionCache (TTL)
│   ├── concurrency/            # NutritionPipeline (asyncio.gather + Semaphore)
│   ├── storage/                # asyncpg pool (db.py) + SQL repo (repository.py)
│   └── static/index.html       # browser demo UI
│
├── tests/                      # 158 tests, all offline
├── artefacts/                  # benchmark results, test reports, sample API outputs
├── data/                       # sample meal images
├── docker-compose.yml          # PostgreSQL + pgAdmin
├── Dockerfile                  # production image
└── TOPIC.md                    # full course requirements
```

---

## Architecture

```
Browser / curl
      │
      ▼
FastAPI  api.py
  ├── POST /analyze
  │     ├── validate_image_bytes()
  │     ├── AIService.identify_ingredients()   ← retry + 60s timeout
  │     │       └── ai.identify_ingredients()  ← Gemini / Anthropic / OpenAI
  │     ├── NutritionPipeline.fetch_all()      ← asyncio.gather + Semaphore(10)
  │     │       ├── NutritionCache (TTL 24h)
  │     │       └── ai.USDAProvider.lookup()   ← retry + 20s timeout
  │     ├── compute_totals()
  │     └── repository.save()                  ← asyncpg → PostgreSQL
  │
  └── GET /history  → repository.list_recent() → PostgreSQL
```

---

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `LLM_PROVIDER` | `anthropic` | VLM provider (`anthropic` / `openai` / `gemini`) |
| `LLM_MODEL` | — | Model ID (e.g. `gemini-2.5-flash`) |
| `ANTHROPIC_API_KEY` | — | Required when `LLM_PROVIDER=anthropic` |
| `OPENAI_API_KEY` | — | Required when `LLM_PROVIDER=openai` |
| `GOOGLE_API_KEY` | — | Required when `LLM_PROVIDER=gemini` |
| `USDA_API_KEY` | — | [Free USDA key](https://fdc.nal.usda.gov/api-key-signup) |
| `POSTGRES_HOST` | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `foodanalyzer` | Database name |
| `POSTGRES_USER` | `postgres` | Database user |
| `POSTGRES_PASSWORD` | `dev` | Database password |
| `NUTRITION_CACHE_TTL_SECONDS` | `86400` | Cache TTL (24 h) |
| `MAX_IMAGE_SIZE_MB` | `5` | Upload size limit |
| `MAX_PARALLEL` | `10` | Max concurrent USDA calls |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

Full list and defaults: `.env.example`.

---

## SE layer — what we built

| Requirement | Implementation |
|-------------|----------------|
| Typed config | `pydantic-settings` `Settings` class, `get_settings()` cached |
| Image validation | Magic-byte check (JPEG/PNG), size limit, early rejection |
| Structured logging | `StructuredFormatter` — human + `key=value` extras; JSON mode via `LOG_FORMAT=json` |
| Retries | `tenacity` `AsyncRetrying` — exponential backoff 2 s → 30 s, 4 attempts |
| Cache | In-memory TTL cache with `asyncio.Lock`, case-insensitive keys |
| Concurrency | `asyncio.gather` + `Semaphore(max_parallel)` — N ingredients in ~1 call time |
| Storage | `asyncpg` pool, `analyses` table (JSONB), `RETURNING id, created_at` |
| HTTP API | FastAPI `POST /analyze` + `GET /history` (pagination), lifespan pool management |
| CLI | `python -m foodanalyzer analyze <path> [--offline] [--json]` |
| Tests | 158 tests across 12 files, all offline, `pytest-asyncio` |
| Docker | `python:3.12-slim`, non-root user, `uvicorn` CMD |
| Demo UI | Single-page HTML at `GET /` — drag-and-drop upload, results table, history |

---

## Git workflow

- `main` is protected — all changes via Pull Request
- Branch naming: `<name>/<short-description>` (e.g. `aysel/config-loader`)
- Every PR requires ≥1 teammate review
- Final release tag: `v1.0-final`

---

## Team

**Project:** AI Food Analyzer | **Group:** Byte Bite

| # | Member | GitHub | Focus |
|---|--------|--------|-------|
| 1 | Rəhimə Kərimova | [@RahimaKarimova](https://github.com/RahimaKarimova) | Storage (asyncpg pool, repository), analyzer wiring, structured logging |
| 2 | Gülnur Məmmədova | [@gulnurmammadova](https://github.com/gulnurmammadova) | AIService (retry+timeout), NutritionCache (TTL), NutritionPipeline (concurrency), test artifacts |
| 3 | Şəmistan Hüseynov | [@Shamistanh](https://github.com/Shamistanh) | FastAPI endpoints (POST /analyze, GET /history), API tests |
| 4 | Aysel Mamedova | [@AMammedova](https://github.com/AMammedova) | Config, models, validation, CLI, Docker, web UI, project setup |
