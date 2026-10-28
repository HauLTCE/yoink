"""Hierarchical .gitignore and .yoinkignore filtering engine."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

ALWAYS_IGNORE: tuple[str, ...] = (
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "target",
    "vendor",
    ".gradle",
    ".idea",
    ".vscode",
    ".dart_tool",
    "_build",
    "deps",
    ".yoink-cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
)

_IGNORE_FILENAMES = (".gitignore", ".yoinkignore")


@dataclass(frozen=True)
class _Pattern:
    base_parts: tuple[str, ...]
    regex: re.Pattern[str]
    negated: bool
    dir_only: bool
    anchored: bool


def _glob_to_regex(pat: str) -> str:
    i = 0
    n = len(pat)
    out: list[str] = []
    while i < n:
        c = pat[i]
        if c == "*":
            if i + 1 < n and pat[i + 1] == "*":
                if i + 2 < n and pat[i + 2] == "/":
                    out.append("(?:.+/)?")
                    i += 3
                    continue
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = i + 1
            if j < n and pat[j] in ("!", "^"):
                j += 1
            if j < n and pat[j] == "]":
                j += 1
            while j < n and pat[j] != "]":
                j += 1
            if j < n:
                inner = pat[i + 1 : j].replace("\\", "\\\\")
                if inner.startswith("!"):
                    inner = "^" + inner[1:]
                out.append(f"[{inner}]")
                i = j + 1
                continue
            out.append(re.escape(c))
        else:
            out.append(re.escape(c))
        i += 1
    return "".join(out)


def _compile_pattern(line: str, base_parts: tuple[str, ...]) -> _Pattern | None:
    raw = line.rstrip("\r\n")
    if not raw or raw.lstrip().startswith("#"):
        return None
    negated = False
    if raw.startswith("!"):
        negated = True
        raw = raw[1:]
    raw = raw.strip()
    if not raw:
        return None
    dir_only = raw.endswith("/")
    if dir_only:
        raw = raw.rstrip("/")
    anchored = raw.startswith("/") or ("/" in raw)
    raw = raw.lstrip("/")
    body = _glob_to_regex(raw)
    if anchored:
        rx = re.compile(f"^{body}(?:/.*)?$")
    else:
        rx = re.compile(f"^(?:.+/)?{body}(?:/.*)?$")
    return _Pattern(
        base_parts=base_parts,
        regex=rx,
        negated=negated,
        dir_only=dir_only,
        anchored=anchored,
    )


def _parse_ignore_file(path: Path, root: Path) -> list[_Pattern]:
    try:
        rel_parent = path.parent.resolve().relative_to(root.resolve())
        base_parts = () if str(rel_parent) == "." else rel_parent.parts
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except (OSError, ValueError):
        return []
    pats: list[_Pattern] = []
    for line in lines:
        p = _compile_pattern(line, base_parts)
        if p is not None:
            pats.append(p)
    return pats


def load_ignore(root: Path) -> Callable[[Path, bool], bool]:
    """Return a predicate `(path, is_dir) -> bool` checking if path is ignored."""
    root = Path(root).resolve()
    patterns: list[_Pattern] = []
    for name in _IGNORE_FILENAMES:
        top = root / name
        if top.is_file():
            patterns.extend(_parse_ignore_file(top, root))

    always_set = frozenset(ALWAYS_IGNORE)

    def _is_ignored(path: Path, is_dir: bool = False) -> bool:
        try:
            rel = Path(path).resolve().relative_to(root)
        except ValueError:
            return False
        parts = rel.parts
        if not parts:
            return False
        if any(part in always_set for part in parts):
            return True
        rel_posix = rel.as_posix()
        state = False
        for pat in patterns:
            if pat.base_parts:
                if parts[: len(pat.base_parts)] != pat.base_parts:
                    continue
                sub_parts = parts[len(pat.base_parts) :]
                if not sub_parts:
                    continue
                sub_posix = "/".join(sub_parts)
            else:
                sub_posix = rel_posix
            if pat.dir_only and not is_dir:
                parent_parts = sub_posix.split("/")[:-1]
                if not parent_parts:
                    continue
                matched = any(
                    pat.regex.match("/".join(parent_parts[: idx + 1]))
                    for idx in range(len(parent_parts))
                )
            else:
                matched = bool(pat.regex.match(sub_posix))
            if matched:
                state = not pat.negated
        return state

    return _is_ignored


def iter_files(root: Path, ignored: Callable[[Path, bool], bool] | None = None) -> Iterator[Path]:
    """Recursively yield non-ignored files under `root` in deterministic order."""
    root = Path(root).resolve()
    if ignored is None:
        ignored = load_ignore(root)

    def _walk(cur: Path) -> Iterator[Path]:
        try:
            entries = sorted(cur.iterdir(), key=lambda p: p.name)
        except OSError:
            return
        for entry in entries:
            is_dir = entry.is_dir()
            if entry.is_symlink():
                try:
                    target = entry.resolve()
                    if not target.is_relative_to(root):
                        continue
                except OSError:
                    continue
            if ignored(entry, is_dir):
                continue
            if is_dir:
                yield from _walk(entry)
            elif entry.is_file():
                yield entry

    yield from _walk(root)
