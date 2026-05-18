## What this PR changes

<!-- 1-3 sentences. The reviewer should know the scope before reading any diff. -->

## Why

Closes #_[issue]_

## How I tested it

- [ ] `pytest` passes locally
- [ ] `pytest tests/test_ai_smoke.py` (provided smoke tests) passes
- [ ] Coverage stayed at or above the threshold (run `pytest --cov`)
- [ ] If touching `Dockerfile` or `requirements.txt`: `docker build .` succeeds

## What this PR does NOT do

## Checklist

- [ ] No `.env`, secrets, or other private files in the diff
- [ ] No `TODO` / `FIXME` comments left in the changed code
- [ ] Type hints on every new public function / method
- [ ] No `except Exception: pass` or bare `except:`
- [ ] No `print()` for runtime diagnostics — use `logging`
- [ ] The provided `ai/` package's public interface is unchanged
- [ ] If using an AI assistant: I can explain every line of code below

## AI assistant disclosure

_[none / describe]_
