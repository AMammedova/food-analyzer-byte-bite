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

| Member | GitHub | Focus |
|--------|--------|-------|
| _[name]_ | _[@handle]_ | _[area]_ |

_Update this table as you assign work._

## AI assistant disclosure

_[Update in the final report — e.g. Cursor used for scaffolding; team owns all merged code.]_
