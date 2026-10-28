"""SPDX-flavored license sniffing from root LICENSE/COPYING files."""

from __future__ import annotations

from pathlib import Path

_PREFIXES = ("LICENSE", "LICENCE", "COPYING")
_READ_BYTES = 8192


def find_license_file(root: Path) -> Path | None:
    """First top-level LICENSE*/COPYING*/LICENCE* file under root."""
    try:
        for child in sorted(Path(root).iterdir()):
            if child.is_file() and child.name.upper().startswith(_PREFIXES):
                return child
    except OSError:
        return None
    return None


def _classify(text: str) -> str:
    t = text.lower()

    if "apache license" in t and "version 2" in t:
        return "Apache-2.0"
    if "mozilla public license" in t and "2.0" in t:
        return "MPL-2.0"
    if "gnu lesser general public license" in t or "lgpl" in t:
        return "LGPL-2.1"
    if "gnu general public license" in t:
        if "version 3" in t or "gplv3" in t or "gpl-3" in t:
            return "GPL-3.0"
        if "version 2" in t or "gplv2" in t or "gpl-2" in t:
            return "GPL-2.0"
        return "GPL-3.0"  # shrug, latest wins
    if "the unlicense" in t or "unlicense.org" in t:
        return "Unlicense"
    if "redistribution and use in source and binary forms" in t:
        if "neither the name" in t or "nor the names" in t:
            return "BSD-3-Clause"
        return "BSD-2-Clause"
    # mit last-ish: its phrases are generic enough to false-positive elsewhere
    if "permission is hereby granted, free of charge" in t and (
        "the software" in t or "mit license" in t
    ):
        return "MIT"
    return "other"


def detect_license(root: Path) -> str | None:
    """Best-effort SPDX id for the repo's root license file."""
    lic = find_license_file(root)
    if lic is None:
        return None
    try:
        head = lic.read_bytes()[:_READ_BYTES].decode("utf-8", errors="replace")
    except OSError:
        return None
    if not head.strip():
        return None
    return _classify(head)


__all__ = ["detect_license", "find_license_file"]
