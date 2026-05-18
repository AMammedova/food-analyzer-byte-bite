"""Tests for logging setup (offline)."""

from __future__ import annotations

import logging

from foodanalyzer.logging_config import setup_logging


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
