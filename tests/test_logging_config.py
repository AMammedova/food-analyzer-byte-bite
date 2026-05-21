"""Tests for logging setup — formatter selection and extras handling."""

from __future__ import annotations

import io
import json
import logging
import os

import pytest

from foodanalyzer import logging_config
from foodanalyzer.logging_config import (
    JsonFormatter,
    StructuredFormatter,
    setup_logging,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def make_record(
    *,
    message: str = "event_happened",
    level: int = logging.INFO,
    extras: dict | None = None,
) -> logging.LogRecord:
    """Build a LogRecord with optional `extra=` attributes attached."""
    record = logging.LogRecord(
        name="foodanalyzer.test",
        level=level,
        pathname=__file__,
        lineno=10,
        msg=message,
        args=(),
        exc_info=None,
    )
    if extras:
        for key, value in extras.items():
            setattr(record, key, value)
    return record


# ─────────────────────────────────────────────────────────────────────────────
# setup_logging — level + handler hygiene
# ─────────────────────────────────────────────────────────────────────────────


def test_setup_logging_sets_level() -> None:
    setup_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG


def test_setup_logging_info_level() -> None:
    setup_logging("INFO")
    assert logging.getLogger().level == logging.INFO


def test_setup_logging_does_not_duplicate_handlers() -> None:
    setup_logging("INFO")
    setup_logging("INFO")
    assert len(logging.getLogger().handlers) == 1


def test_setup_logging_unknown_level_falls_back_to_info() -> None:
    setup_logging("LOUD")
    assert logging.getLogger().level == logging.INFO


# ─────────────────────────────────────────────────────────────────────────────
# StructuredFormatter
# ─────────────────────────────────────────────────────────────────────────────


class TestStructuredFormatter:

    def test_renders_message_without_extras(self):
        out = StructuredFormatter().format(make_record())
        assert "INFO" in out
        assert "foodanalyzer.test" in out
        assert "event_happened" in out
        # No trailing `=` means no extras section.
        assert "=" not in out

    def test_appends_extras_as_key_value_pairs(self):
        out = StructuredFormatter().format(
            make_record(extras={"ingredient": "rice", "ms": 12.5})
        )
        assert 'ingredient="rice"' in out
        assert "ms=12.5" in out

    def test_extras_with_quotes_are_escaped(self):
        # `name` is a reserved LogRecord attribute, so use a custom key
        # to test that special characters are JSON-escaped in the output.
        out = StructuredFormatter().format(
            make_record(extras={"label": 'has "quote"'})
        )
        assert 'label="has \\"quote\\""' in out

    def test_non_json_serializable_value_falls_back_to_str(self):
        class Custom:
            def __str__(self) -> str:
                return "<custom>"

        out = StructuredFormatter().format(make_record(extras={"obj": Custom()}))
        assert "<custom>" in out


# ─────────────────────────────────────────────────────────────────────────────
# JsonFormatter
# ─────────────────────────────────────────────────────────────────────────────


class TestJsonFormatter:

    def test_emits_one_json_object(self):
        line = JsonFormatter().format(make_record())
        payload = json.loads(line)
        assert payload["level"] == "INFO"
        assert payload["logger"] == "foodanalyzer.test"
        assert payload["message"] == "event_happened"
        assert "timestamp" in payload

    def test_extras_become_top_level_fields(self):
        line = JsonFormatter().format(
            make_record(extras={"ingredient": "rice", "ms": 12.5})
        )
        payload = json.loads(line)
        assert payload["ingredient"] == "rice"
        assert payload["ms"] == 12.5

    def test_standard_record_attributes_are_filtered(self):
        line = JsonFormatter().format(make_record())
        payload = json.loads(line)
        for noise_key in ("args", "msg", "pathname", "process", "thread"):
            assert noise_key not in payload

    def test_exc_info_is_serialized_when_present(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            record = make_record()
            record.exc_info = sys.exc_info()
            line = JsonFormatter().format(record)
        payload = json.loads(line)
        assert "exc_info" in payload
        assert "ValueError" in payload["exc_info"]


# ─────────────────────────────────────────────────────────────────────────────
# Formatter selection via LOG_FORMAT env
# ─────────────────────────────────────────────────────────────────────────────


class TestFormatterSelection:

    def test_default_is_structured_text(self, monkeypatch):
        monkeypatch.delenv("LOG_FORMAT", raising=False)
        formatter = logging_config._select_formatter()
        assert isinstance(formatter, StructuredFormatter)

    def test_json_env_selects_json_formatter(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "json")
        formatter = logging_config._select_formatter()
        assert isinstance(formatter, JsonFormatter)

    def test_case_insensitive_env(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "JSON")
        formatter = logging_config._select_formatter()
        assert isinstance(formatter, JsonFormatter)

    def test_unknown_value_falls_back_to_text(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "yaml")
        formatter = logging_config._select_formatter()
        assert isinstance(formatter, StructuredFormatter)


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end: a real log call goes through the configured handler
# ─────────────────────────────────────────────────────────────────────────────


def test_real_logger_writes_extras_to_handler(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    setup_logging("INFO")

    buf = io.StringIO()
    handler = logging.getLogger().handlers[0]
    monkeypatch.setattr(handler, "stream", buf)

    logging.getLogger("foodanalyzer.smoke").info(
        "smoke_event", extra={"ingredient": "rice", "count": 3}
    )
    handler.flush()

    output = buf.getvalue()
    assert "smoke_event" in output
    assert 'ingredient="rice"' in output
    assert "count=3" in output
