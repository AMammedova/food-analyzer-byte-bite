# Architecture (draft)

_Update this diagram as the SE layer grows._

```mermaid
flowchart LR
  subgraph entry [Entry points]
    CLI[CLI foodanalyzer]
    API[FastAPI POST /analyze]
  end

  subgraph se [SE layer — src/foodanalyzer]
    CFG[config]
    VAL[validation]
    SVC[ai_service retries cache]
    PIPE[concurrency pipeline]
    REPO[(PostgreSQL history)]
  end

  subgraph ai [Provided ai/ — do not edit]
    VLM[identify_ingredients]
    NUT[NutritionProvider]
    CALC[compute_totals]
  end

  CLI --> VAL
  API --> VAL
  VAL --> SVC
  SVC --> VLM
  SVC --> PIPE
  PIPE --> NUT
  SVC --> CALC
  SVC --> REPO
```

## Status

| Component | Owner | Status |
|-----------|-------|--------|
| `config.py` | — | not started |
| CLI `analyze` | — | not started |
| HTTP `POST /analyze` | — | not started |
| PostgreSQL repository | — | not started |
| Nutrition cache + TTL | — | not started |
| Parallel nutrition lookups | — | not started |
| Retries / backoff | — | not started |
| Dockerfile | — | not started |
