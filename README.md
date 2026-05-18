# Food Analyzer — Byte Bite

> Upload a meal photo → identify ingredients with estimated portions → nutrition lookup → calories and macro totals.

**Team:** Byte Bite  
**Topic:** 2 — AI Food Analyzer  
**Course:** AI-ENG-110 Software Engineering, AI Academy  
**Repository:** https://github.com/AMammedova/food-analyzer-byte-bite  
**Due:** May 23, 2026 at 23:59 (UTC+4)

---

## Quick start

```bash
git clone https://github.com/AMammedova/food-analyzer-byte-bite.git
cd food-analyzer-byte-bite
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt

cp .env.example .env          # fill API keys when using live providers

python data/_make_samples.py  # one-time: generate sample PNGs
python demo_ai.py --offline
pytest tests/test_ai_smoke.py -v
```

## Docker Compose (PostgreSQL + pgAdmin)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
cp .env.example .env    # POSTGRES_* must match docker-compose.yml

docker compose up -d    # starts db + pgadmin
docker compose ps       # db should be healthy
docker compose down     # stop
docker compose down -v  # stop and delete DB volume
```

### Database credentials (local dev)

| Variable | Default | Used by |
|----------|---------|---------|
| `POSTGRES_USER` | `postgres` | `db` service, Python `config.py` |
| `POSTGRES_PASSWORD` | `dev` | same |
| `POSTGRES_DB` | `foodanalyzer` | same |
| `POSTGRES_HOST` | `localhost` | Python on your PC → `localhost` |
| `POSTGRES_PORT` | `5433` | host port (5433 if local PostgreSQL uses 5432) |

`DATABASE_URL` is built automatically from `POSTGRES_*` if not set explicitly.

### pgAdmin

| Variable | Default |
|----------|---------|
| `PGADMIN_DEFAULT_EMAIL` | `admin@bytebite.local` |
| `PGADMIN_DEFAULT_PASSWORD` | `admin` |
| `PGADMIN_PORT` | `5051` |

1. Open http://localhost:5051  
2. Log in with the email/password above.  
3. Server **Food Analyzer (Byte Bite)** is pre-configured (connects to `db` inside Docker).  

If you change `POSTGRES_PASSWORD` in `.env`, also update `docker/pgadmin/servers.json` (`Password` field).

## Project layout

```
food-analyzer-byte-bite/
├── ai/                 # provided — do not edit
├── data/               # sample meal images
├── demo_ai.py          # offline/online AI demo
├── src/foodanalyzer/   # your SE layer (CLI, API, storage, …)
├── tests/              # smoke tests + your tests
├── docs/               # architecture, notes
└── TOPIC.md            # full requirements from course
```

## What we are building

See `TOPIC.md` and `docs/architecture.md`. Minimum deliverables:

- `python -m foodanalyzer analyze <image>` — CLI totals table
- `POST /analyze` — multipart image upload (FastAPI)
- PostgreSQL history log, nutrition cache (24h TTL), parallel lookups, retries
- ≥60% test coverage (offline), Dockerfile

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `LLM_PROVIDER` | `anthropic` | VLM provider |
| `LLM_MODEL` | — | Model id |
| `NUTRITION_PROVIDER` | `usda` | Nutrition backend |
| `USDA_API_KEY` | — | [Free USDA key](https://fdc.nal.usda.gov/api-key-signup) |
| `DATABASE_URL` | see `.env.example` | PostgreSQL |
| `NUTRITION_CACHE_TTL_SECONDS` | `86400` | Cache TTL |
| `MAX_IMAGE_SIZE_MB` | `5` | Upload limit |
| `LOG_LEVEL` | `INFO` | Logging |

Full list: `.env.example`. **Never commit `.env`.**

## Git workflow

- `main` is protected — changes via PR only
- Branch: `<name>/<short-description>` (e.g. `aisel/config-loader`)
- Every PR needs ≥1 teammate review
- Final tag: `v1.0-final`

## Team

**Project:** AI Food Analyzer  
**Group:** Byte Bite

| # | Member | GitHub | Focus |
|---|--------|--------|-------|
| 1 | Rəhimə Kərimova | [@RahimaKarimova](https://github.com/RahimaKarimova) | _[area]_ |
| 2 | Gülnur Məmmədova | [@gulnurmammadova](https://github.com/gulnurmammadova) | _[area]_ |
| 3 | Şəmistan Hüseynov | [@Shamistanh](https://github.com/Shamistanh) | _[area]_ |
| 4 | Aysel Mamedova | [@AMammedova](https://github.com/AMammedova) | _[area]_ |

_Update **Focus** columns as you assign tasks._

