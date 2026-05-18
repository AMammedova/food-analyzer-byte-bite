from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# JPEG: FF D8
# PNG:  89 50 4E 47  (= \x89PNG)
_MAGIC: dict[str, bytes] = {
    "JPEG": b"\xff\xd8",
    "PNG": b"\x89\x50\x4e\x47",
}

_MAGIC_READ_BYTES = 4


class ValidationError(ValueError):
    """Raised when an uploaded image fails format or size checks.

    Inherits ValueError so callers can catch it without importing this module.
    But explicit catching of ValidationError is preferred for clarity.
    """


def validate_image_path(path: str | Path, max_bytes: int) -> Path:
    p = Path(path)

    if not p.is_file():
        raise ValidationError(f"Image file not found: {p}")

    size = p.stat().st_size
    if size > max_bytes:
        limit_mb = max_bytes / (1024 * 1024)
        actual_mb = size / (1024 * 1024)
        raise ValidationError(
            f"Image too large: {actual_mb:.1f} MB (limit {limit_mb:.0f} MB): {p.name}"
        )

    with p.open("rb") as f:
        header = f.read(_MAGIC_READ_BYTES)

    detected = _detect_format(header)
    if detected is None:
        raise ValidationError(
            f"Unsupported format: only JPEG and PNG are accepted. "
            f"Got unrecognized header bytes: {header.hex()!r}: {p.name}"
        )

    logger.debug("Image validated: %s  format=%s  size=%d bytes", p.name, detected, size)
    return p


def validate_image_bytes(data: bytes, filename: str, max_bytes: int) -> str:

    if len(data) > max_bytes:
        limit_mb = max_bytes / (1024 * 1024)
        actual_mb = len(data) / (1024 * 1024)
        raise ValidationError(
            f"Upload too large: {actual_mb:.1f} MB (limit {limit_mb:.0f} MB): {filename}"
        )

    if len(data) < _MAGIC_READ_BYTES:
        raise ValidationError(f"File is empty or too small: {filename}")

    detected = _detect_format(data[:_MAGIC_READ_BYTES])
    if detected is None:
        raise ValidationError(
            f"Unsupported format: only JPEG and PNG are accepted: {filename}"
        )

    logger.debug("Upload validated: %s  format=%s  size=%d bytes", filename, detected, len(data))
    return detected


def _detect_format(header: bytes) -> str | None:
    for fmt, magic in _MAGIC.items():
        if header[: len(magic)] == magic:
            return fmt
    return None
