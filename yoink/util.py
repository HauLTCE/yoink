"""Small shared helpers."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path


def sha256_short(text: str) -> str:
    """First 16 hex chars of the sha256 of text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def iso_now() -> str:
    """UTC timestamp, iso8601."""
    return datetime.now(timezone.utc).isoformat()


def read_text(path: Path) -> str:
    """utf-8, errors=replace."""
    return path.read_text(encoding="utf-8", errors="replace")


def find_source_root(root: Path) -> Path:
    """root/'src' if it exists and has .py files, else root."""
    src = root / "src"
    if src.is_dir() and any(src.rglob("*.py")):
        return src
    return root


def posix_rel(path: Path, root: Path) -> str:
    """path relative to root, posix separators."""
    return path.relative_to(root).as_posix()
