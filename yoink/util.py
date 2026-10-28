"""File system, hashing, source root discovery, and path safety utilities."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from yoink.errors import EmitError


def sha256_short(text: str) -> str:
    """Return the first 16 hex chars of the UTF-8 SHA-256 digest."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def iso_now() -> str:
    """Return current UTC ISO-8601 timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_text(path: Path) -> str:
    """Read UTF-8 text from path, replacing invalid sequences."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


_SOURCE_LAYOUT_DIRS = (
    "src/main/java",
    "src/main/kotlin",
    "src/main/scala",
    "src",
    "lib",
    "Sources",
)

_CODE_EXTS = {
    ".py", ".pyi",
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts",
    ".go", ".rs",
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx",
    ".cs", ".java", ".kt", ".kts", ".scala", ".sc",
    ".php", ".rb", ".swift", ".dart", ".lua", ".ex", ".exs",
}


def find_source_root(root: Path, language: str | None = None) -> Path:
    """Discover the logical source root for a repository layout."""
    root = Path(root).resolve()
    if language in ("go", "dart", "php", "csharp", "cpp"):
        # Go modules, Dart packages, PHP PSR-4, C#, and C/C++ resolve relative to repo root
        # (or handle lib/ internally in their resolvers)
        if language == "dart" and (root / "lib").is_dir():
            return root / "lib"
        return root

    if language == "java":
        cand = root / "src" / "main" / "java"
        if cand.is_dir():
            return cand
    elif language == "kotlin":
        for sub in ("src/main/kotlin", "src/main/java"):
            cand = root / sub
            if cand.is_dir():
                return cand
    elif language == "scala":
        cand = root / "src" / "main" / "scala"
        if cand.is_dir():
            return cand
    elif language == "swift":
        cand = root / "Sources"
        if cand.is_dir():
            return cand
    elif language in ("ruby", "elixir"):
        cand = root / "lib"
        if cand.is_dir():
            return cand

    # Python / Rust / JS-TS / general check for src/ layout
    src_dir = root / "src"
    if src_dir.is_dir():
        # If there are no code files directly in root (excluding setup.py / build scripts),
        # and src/ has code files, treat src/ as source root.
        root_code = [
            p for p in root.iterdir()
            if p.is_file() and p.suffix in _CODE_EXTS and p.name not in ("setup.py", "conftest.py", "build.rs")
        ]
        src_has_code = any(p.is_file() and p.suffix in _CODE_EXTS for p in src_dir.rglob("*"))
        if src_has_code and not root_code:
            return src_dir

    return root


def posix_rel(path: Path, root: Path) -> str:
    """Compute POSIX relative path from root."""
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        try:
            return Path(path).relative_to(Path(root)).as_posix()
        except ValueError:
            return Path(path).name


def ensure_safe_write_path(dest: Path, out_root: Path) -> Path:
    """Ensure `dest` resolves strictly inside `out_root` to prevent path traversal."""
    resolved_root = Path(out_root).resolve()
    resolved_dest = Path(dest).resolve()
    if resolved_dest != resolved_root and not resolved_dest.is_relative_to(resolved_root):
        raise EmitError(f"unsafe output path escapes output directory: {dest}")
    return resolved_dest
