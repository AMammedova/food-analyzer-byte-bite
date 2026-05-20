# Storage (PostgreSQL history)

Analysis history is stored in PostgreSQL via **asyncpg** (`storage/db.py`, `storage/repository.py`).

## Configuration

Connection settings come from `foodanalyzer.config.Settings`:

| Source | Description |
|--------|-------------|
| `DATABASE_URL` | Full DSN (optional) |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT` | Used to build URL if `DATABASE_URL` is unset |

Built default (see `config.py`):

```
postgresql+asyncpg://postgres:dev@localhost:5432/foodanalyzer
```

`storage/db.py` converts `postgresql+asyncpg://` → `postgresql://` for asyncpg.

Local dev with Docker Compose typically uses host port **5433** — set `POSTGRES_PORT=5433` in `.env` to match `docker-compose.yml`.

## Schema

Table `analyses` (created on API startup if missing):

| Column | Type | Description |
|--------|------|-------------|
| `id` | `BIGSERIAL` | Primary key |
| `created_at` | `TIMESTAMPTZ` | Insert time (default `NOW()`) |
| `image_path` | `TEXT` | Path or label for the image |
| `ingredients` | `JSONB` | Array of ingredient rows (`IngredientOut`) |
| `totals` | `JSONB` | Meal totals (`TotalsOut`) |

## Repository API

### `save(pool, record) -> AnalysisRecord`

Insert one row. Returns the record with `id` and `created_at` populated.

Called from `api.py` after a successful `analyze()`.

### `list_recent(pool, *, limit=20) -> list[AnalysisRecord]`

Return up to `limit` rows, **newest first**.

Used by `GET /history`.

## Connection pool

| Function | When |
|----------|------|
| `create_pool(settings)` | API lifespan startup |
| `init_schema(pool)` | Ensures `analyses` table exists |
| `close_pool(pool)` | API lifespan shutdown |

Pool sizing: `min_size=1`, `max_size=10`.

## Models

- **`AnalysisResult`** — API/CLI response (no DB id).
- **`AnalysisRecord`** — persisted row; use `AnalysisRecord.from_result(result)` before insert.

See `src/foodanalyzer/models.py`.

## Inspecting data

With Docker Compose + pgAdmin (see root `README.md`):

1. http://localhost:5051
2. Connect to server **Food Analyzer (Byte Bite)**
3. Query: `SELECT id, created_at, image_path FROM analyses ORDER BY created_at DESC LIMIT 20;`

## Tests

API unit tests (`tests/test_api.py`) replace the database with `InMemoryHistory` on `app.state.history_repo` — repository functions are not hit.

Integration tests against a real Postgres instance are optional and not required for grading smoke tests.
