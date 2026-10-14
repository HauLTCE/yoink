"""Zip emit: pack an emitted bundle dir into one archive."""

from __future__ import annotations

import zipfile
from pathlib import Path


def emit_zip(
    out_dir: Path,
    zip_path: Path | None = None,
    *,
    default_name: str = "yoink-bundle",
) -> Path:
    """Zip everything under out_dir; return the archive path."""
    out_dir = Path(out_dir)
    if zip_path is None:
        zip_path = out_dir.parent / f"{default_name}.zip"
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(out_dir.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(out_dir).as_posix())
    return zip_path
