"""Logging setup for the SE layer.

Why a custom formatter
----------------------
The codebase emits structured events everywhere:

    logger.info("nutrition_lookup_started", extra={"ingredient": name})

The default `logging.Formatter` shows only `%(message)s` and silently drops
everything passed via `extra=`. With a plain-text format, the structured
metadata never makes it to the console or log file — the cost of writing
`extra={...}` everywhere is paid, but no observability value is delivered.

`StructuredFormatter` keeps the human-readable prefix
(`%(asctime)s %(levelname)s %(name)s: %(message)s`) and appends every
non-standard attribute on the `LogRecord` as `key=value` pairs. The format
stays grep-friendly for local development and machine-parseable for log
aggregation (Loki, Elasticsearch, etc.) without pulling in a JSON-logger
dependency.

Output mode is controlled by the `LOG_FORMAT` env var:

    LOG_FORMAT=text   (default) human + key=value extras
    LOG_FORMAT=json   one JSON object per line (for prod log shippers)

Switching to JSON later is a one-line formatter swap — the call sites
do not change.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

# Standard LogRecord attributes that should NOT be treated as structured
# extras. Anything else attached to a record came from `extra={...}` or
# `LoggerAdapter` and is part of the structured payload.
#
# Source: https://docs.python.org/3/library/logging.html#logrecord-attributes
_STANDARD_RECORD_KEYS: frozenset[str] = frozenset({
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
})


def _extract_extras(record: logging.LogRecord) -> dict[str, Any]:
    """Return only the user-supplied `extra={...}` attributes from a record."""
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in _STANDARD_RECORD_KEYS and not key.startswith("_")
    }


class StructuredFormatter(logging.Formatter):
    """Human-readable line + space-separated `key=value` for any extras."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = _extract_extras(record)
        if not extras:
            return base
        # `json.dumps` keeps values safe for logs (escapes quotes, newlines).
        tail = " ".join(f"{k}={json.dumps(v, default=str)}" for k, v in extras.items())
        return f"{base} {tail}"


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Suitable for log shippers like Loki."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(_extract_extras(record))
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _select_formatter() -> logging.Formatter:
    """Pick the formatter based on LOG_FORMAT env (text default)."""
    return JsonFormatter() if os.getenv("LOG_FORMAT", "text").lower() == "json" else StructuredFormatter()


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with one handler and the selected formatter.

    Re-running this function replaces existing handlers — callers that
    invoke `setup_logging` multiple times (CLI, tests) will not accumulate
    duplicate output.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)
    handler.setFormatter(_select_formatter())

    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.handlers.clear()
    root.addHandler(handler)
