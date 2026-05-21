# HTTP API

FastAPI application: `src/foodanalyzer/api.py`.

## Run the server

1. Start PostgreSQL (history persistence):

   ```bash
   docker compose up -d
   ```

2. Configure env (see `.env.example`):

   ```bash
   cp .env.example .env
   # POSTGRES_HOST=localhost, POSTGRES_PORT=5433, etc.
   ```

3. Start uvicorn:

   ```bash
   uvicorn foodanalyzer.api:app --host 0.0.0.0 --port 8000 --reload
   ```

   Default port can also be set via `HTTP_PORT` in settings (uvicorn flag still required unless you add a launcher).

Interactive docs: http://localhost:8000/docs

## Endpoints

### `GET /health`

Liveness check.

**Response** `200 OK`

```json
{"status": "ok"}
```

```bash
curl -s http://localhost:8000/health
```

---

### `POST /analyze`

Analyze a meal image.

| Item | Value |
|------|--------|
| Content-Type | `multipart/form-data` |
| Field name | `file` |
| Formats | JPEG, PNG |
| Max size | `MAX_IMAGE_SIZE_MB` (default 5 MB) |

**Success** `200 OK` — body matches `AnalysisResult`:

```json
{
  "meal_recognized": true,
  "image_path": "uploads/abc123_meal.png",
  "ingredients": [
    {
      "name": "white rice (cooked)",
      "estimated_grams": 200.0,
      "confidence": 0.9,
      "kcal": 260.0,
      "protein_g": 5.4,
      "carbs_g": 56.0,
      "fat_g": 0.6
    }
  ],
  "totals": {
    "kcal": 260.0,
    "protein_g": 5.4,
    "carbs_g": 56.0,
    "fat_g": 0.6
  }
}
```

When no meal is detected, `meal_recognized` is `false` and `ingredients` / `totals` are empty — still `200 OK`.

```bash
curl -s -X POST http://localhost:8000/analyze \
  -F "file=@data/rice_chicken_broccoli.png"
```

**Errors**

| Status | Cause |
|--------|--------|
| 422 | Invalid or oversize file (`ValidationError`) |
| 503 | VLM or provider failure (`ProviderError`) |

Example 422 body:

```json
{"detail": "Unsupported format: only JPEG and PNG are accepted: bad.txt"}
```

---

### `GET /history`

Return recent saved analyses (newest first).

| Query param | Default | Range |
|-------------|---------|--------|
| `limit` | `20` | 1–100 |

**Response** `200 OK` — JSON array of `AnalysisRecord` objects (with `id`, `created_at`, `image_path`, `ingredients`, `totals`).

```bash
curl -s "http://localhost:8000/history?limit=10"
```

Requires PostgreSQL; each successful `POST /analyze` appends a row (failures to save are logged but do not fail the analyze response).

## Application lifecycle

On **startup**:

1. Open asyncpg connection pool (`storage/db.py`).
2. Run `CREATE TABLE IF NOT EXISTS analyses ...`.

On **shutdown**:

- Close the pool.

## Implementation notes

- Uploaded files are stored under `UPLOAD_DIR` (default `uploads/`) with a UUID prefix.
- `analyze()` is called with optional `app.state.vlm` / `app.state.nutrition` overrides (used in tests).
- Production uses live providers from env when overrides are not set.

## Tests

```bash
pytest tests/test_api.py -v
```

Uses `httpx.AsyncClient` with `ASGITransport`, fake VLM/nutrition from `tests/conftest.py`, and an in-memory history store — no network or database.
