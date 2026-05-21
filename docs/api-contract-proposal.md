# API contract proposal — error shape and `/history` pagination

**Status:** proposal, awaiting team review.
**Owner:** Rəhimə.
**Affects:** `src/foodanalyzer/api.py` (Şəmistan), the frontend we are about to build.

This document proposes defaults for two API decisions that need to be locked in **before** the frontend depends on them. Both decisions are cheap to make once and expensive to change later.

---

## 1. Error response shape

### Problem

Today the API returns errors like:

```json
{ "detail": "image too large: 12.4 MB (limit 5 MB): meal.png" }
```

A frontend cannot distinguish between:

- the upload exceeded the size cap (user should compress)
- the image format is unsupported (user should pick a JPEG/PNG)
- the VLM provider is rate-limited (user should retry in 30s)
- the VLM provider is misconfigured (no user action helps)

…even though those four cases need very different UI treatments.

### Proposed shape

```json
{
  "error": {
    "code": "vlm_rate_limited",
    "message": "VLM provider is rate-limited",
    "retryable": true,
    "retry_after_seconds": 30
  }
}
```

- `code` — stable, machine-readable string. Frontend switches UI on this.
- `message` — human-readable, English, safe to show in a toast.
- `retryable` — boolean hint; lets the frontend show a "Retry" button.
- `retry_after_seconds` — present only when the cause has a known cool-down.

### Proposed codes

| HTTP | `code` | When |
|---|---|---|
| 413 | `image_too_large` | Upload exceeds `MAX_IMAGE_SIZE_MB` |
| 422 | `unsupported_format` | Magic bytes are not JPEG/PNG |
| 422 | `image_corrupt` | File is shorter than the magic-byte prefix |
| 422 | `missing_file` | Multipart upload had no file part |
| 429 | `vlm_rate_limited` | Provider returned 429 / equivalent |
| 503 | `vlm_unavailable` | All VLM retries exhausted (non-429) |
| 503 | `nutrition_unavailable` | USDA fully unreachable. **Note:** partial nutrition failures do NOT fail the whole request — analyzer.py already degrades gracefully (per-ingredient zeros) and the response includes the list of skipped names. |
| 500 | `internal_error` | Anything not covered above (bug). |

### Implementation cost

~30 lines in `api.py`:

```python
class ApiError(Exception):
    def __init__(self, *, code: str, message: str, status: int,
                 retryable: bool = False, retry_after_seconds: int | None = None):
        ...

@app.exception_handler(ApiError)
async def api_error_handler(_request, exc: ApiError) -> JSONResponse:
    body = {"error": {"code": exc.code, "message": exc.message, "retryable": exc.retryable}}
    if exc.retry_after_seconds is not None:
        body["error"]["retry_after_seconds"] = exc.retry_after_seconds
    return JSONResponse(status_code=exc.status, content=body)
```

Plus map `ValidationError → ApiError(code="image_too_large" / "unsupported_format" / ...)` and `ProviderError → ApiError(code="vlm_unavailable", retryable=True)`. The existing `validation.py` raises one `ValidationError` for everything — it would need a small refactor to expose the *kind* of failure (an enum on the exception, or distinct subclasses).

---

## 2. `/history` pagination shape

### Problem

Today the endpoint returns a bare list:

```json
[ {record}, {record}, ... ]
```

A frontend cannot answer:

- "Are there more records than what I just got?" (no `has_more` flag)
- "How do I fetch the next page?" (no `offset` or `cursor` parameter)
- "Should I show a 'Load more' button or the end of the list?"

### Proposed shape

```json
{
  "items": [ {record}, {record}, ... ],
  "page": {
    "limit": 20,
    "offset": 0,
    "returned": 20,
    "has_more": true
  }
}
```

Query params: `GET /history?limit=20&offset=40` (defaults: `limit=20`, `offset=0`).

- `limit` — caps at 100 (already does in Şəmistan's branch).
- `offset` — zero-based. Trivially maps to `OFFSET $2` in the SQL.
- `returned` — the actual length of `items` after the DB call.
- `has_more` — `True` iff `returned == limit` AND a `LIMIT limit+1` probe returned `limit+1` rows. Cheap.

### Why offset, not cursor

| | Offset | Cursor |
|---|---|---|
| Implementation | One extra SQL parameter | Encode `(created_at, id)` into an opaque token, decode on the way in |
| Stability under concurrent inserts | Can show a row twice or skip one if new inserts arrive between pages | Stable — cursor pins the boundary |
| When it matters | At ~5+ writes/sec during browsing | Class project: ~0 writes/sec while a user reads history |

**For v1 we propose offset.** Cursors are a one-week migration if traffic ever justifies it; until then they're a code-quality tax with no user benefit.

### Implementation cost in `repository.py`

Already trivially supported — just add `offset` to the function signature:

```python
async def list_recent(conn, limit: int = 20, offset: int = 0) -> list[AnalysisRecord]:
    if limit <= 0:
        return []
    rows = await conn.fetch(
        "SELECT … ORDER BY created_at DESC, id DESC LIMIT $1 OFFSET $2",
        limit, offset,
    )
    return [_row_to_record(row) for row in rows]
```

For `has_more` the API layer asks for `limit+1` and trims:

```python
rows = await repository.list_recent(pool, limit=limit + 1, offset=offset)
has_more = len(rows) > limit
items = rows[:limit]
```

That's the entire feature.

---

## 3. Casing convention

### Problem

The API returns snake_case (`image_path`, `protein_g`). JS/TS convention is camelCase (`imagePath`, `proteinG`). The frontend either translates field-by-field (bug magnet) or accepts Python casing (looks foreign).

### Proposed default

**Keep snake_case on the wire.** Generate the typed TS client from `openapi.json` so the field names are correct by construction — there's nothing to translate manually. If team aesthetics demand camelCase later, add `alias_generator=to_camel` on the Pydantic models once and ship a new client.

This is the cheap default. The opposite default (camelCase on the wire) requires changes on every model and is harder to undo.

---

## 4. CORS

Not in this proposal because Şəmistan owns `api.py`. **The frontend will not work without it.** Şəmistan's branch should add `CORSMiddleware` with explicit allowed origins before we start frontend work:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # dev
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

For prod, add the deployed frontend's URL to `allow_origins` (do **not** use `["*"]` with credentials).

---

## Open questions for the team

1. **Are these codes enough?** Anything we're forgetting? (auth errors don't apply yet — there's no auth.)
2. **`has_more` via `limit+1` probe vs. a separate `COUNT(*)` query?** The probe is cheaper but doesn't give total count. Do we need a total?
3. **Casing — really stick with snake_case?** Vote: comment below or in the team chat.
4. **CORS allowed origins for production** — what's the deployed frontend URL going to be?
