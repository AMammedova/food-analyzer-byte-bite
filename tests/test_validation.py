"""Tests for image validation (all offline — no network, no real AI calls)."""

from __future__ import annotations

import struct
import tempfile
from pathlib import Path

import pytest

from foodanalyzer.validation import (
    ValidationError,
    validate_image_bytes,
    validate_image_path,
)

def _jpeg_bytes(size: int = 100) -> bytes:
    """Return JPEG magic header + padding."""
    return b"\xff\xd8" + b"\x00" * (size - 2)


def _png_bytes(size: int = 100) -> bytes:
    """Return PNG magic header + padding."""
    return b"\x89\x50\x4e\x47" + b"\x00" * (size - 4)


def _write_tmp(content: bytes) -> Path:
    """Write bytes to a temp file and return its Path."""
    f = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
    f.write(content)
    f.close()
    return Path(f.name)

class TestValidateImagePath:
    def test_valid_jpeg_passes(self) -> None:
        p = _write_tmp(_jpeg_bytes())
        result = validate_image_path(p, max_bytes=1024)
        assert result == p

    def test_valid_png_passes(self) -> None:
        p = _write_tmp(_png_bytes())
        result = validate_image_path(p, max_bytes=1024)
        assert result == p

    def test_file_not_found_raises(self) -> None:
        with pytest.raises(ValidationError, match="not found"):
            validate_image_path("/nonexistent/path/photo.jpg", max_bytes=1024)

    def test_oversized_file_raises(self) -> None:
        p = _write_tmp(_jpeg_bytes(200))
        with pytest.raises(ValidationError, match="too large"):
            validate_image_path(p, max_bytes=100)

    def test_wrong_format_raises(self) -> None:
        p = _write_tmp(b"\x25\x50\x44\x46" + b"\x00" * 96)
        with pytest.raises(ValidationError, match="Unsupported format"):
            validate_image_path(p, max_bytes=1024)

    def test_returns_path_object(self) -> None:
        p = _write_tmp(_jpeg_bytes())
        result = validate_image_path(str(p), max_bytes=1024)
        assert isinstance(result, Path)


class TestValidateImageBytes:
    def test_valid_jpeg_bytes_returns_format(self) -> None:
        fmt = validate_image_bytes(_jpeg_bytes(), "photo.jpg", max_bytes=1024)
        assert fmt == "JPEG"

    def test_valid_png_bytes_returns_format(self) -> None:
        fmt = validate_image_bytes(_png_bytes(), "photo.png", max_bytes=1024)
        assert fmt == "PNG"

    def test_oversized_raises(self) -> None:
        with pytest.raises(ValidationError, match="too large"):
            validate_image_bytes(_jpeg_bytes(200), "photo.jpg", max_bytes=100)

    def test_empty_bytes_raises(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            validate_image_bytes(b"\xff", "photo.jpg", max_bytes=1024)

    def test_wrong_magic_raises(self) -> None:
        with pytest.raises(ValidationError, match="Unsupported format"):
            validate_image_bytes(b"\x00\x01\x02\x03" + b"\x00" * 96, "bad.bmp", max_bytes=1024)
