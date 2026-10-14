"""Yoink's own gitignore engine: layered .gitignore + .yoinkignore matching."""

from __future__ import annotations

import fnmatch
import os
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


def load_ignore(root: Path) -> Callable[[Path, bool], bool]:
    """Return ignored(path, is_dir) honoring .gitignore/.yoinkignore at any depth."""
    root = Path(root)
    cache: dict[Path, list[_Pattern]] = {}

    def patterns_for(dirpath: Path) -> list[_Pattern]:
        if dirpath not in cache:
            pats: list[_Pattern] = []
            for name in _IGNORE_FILENAMES:
                pats.extend(_parse_ignore_file(dirpath / name, root))
            cache[dirpath] = pats
        return cache[dirpath]

    def ignored(path: Path, is_dir: bool = False) -> bool:
        try:
            rel = path.relative_to(root)
        except ValueError:
            return False
        parts = rel.parts
        if not parts:
            return False
        for part in parts:
            if part in ALWAYS_IGNORE or fnmatch.fnmatchcase(part, "*.egg-info"):
                return True
        active = list(patterns_for(root))
        for k in range(1, len(parts) + 1):
            last = k == len(parts)
            sub_is_dir = is_dir if last else True
            if k > 1:
                active = active + patterns_for(root.joinpath(*parts[: k - 1]))
            decision: bool | None = None
            for p in active:
                depth = len(p.base_parts)
                if p.base_parts != parts[:depth]:
                    continue
                if p.dir_only and not sub_is_dir:
                    continue
                seg = parts[depth:k]
                if not seg:
                    continue
                candidate = "/".join(seg) if p.anchored else seg[-1]
                if p.regex.fullmatch(candidate):
                    decision = not p.negated
            if decision:
                return True
        return False

    return ignored


def iter_files(root: Path, ignored: Callable[[Path, bool], bool]) -> Iterator[Path]:
    """Yield non-ignored files under root, pruning ignored dirs top-down."""
    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        dirnames[:] = sorted(n for n in dirnames if not ignored(d / n, True))
        for name in sorted(filenames):
            p = d / name
            if not ignored(p, False):
                yield p


def _parse_ignore_file(path: Path, root: Path) -> list[_Pattern]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    try:
        base_parts = path.parent.relative_to(root).parts
    except ValueError:
        return []
    pats: list[_Pattern] = []
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        while line.endswith(" ") and not line.endswith("\\ "):
            line = line[:-1]
        line = line.replace("\\ ", " ")
        if not line or line.startswith("#"):
            continue
        negated = False
        if line.startswith("!"):
            negated = True
            line = line[1:]
        elif line.startswith("\\!") or line.startswith("\\#"):
            line = line[1:]
        if not line:
            continue
        dir_only = line.endswith("/")
        if dir_only:
            line = line[:-1]
        anchored = "/" in line
        if line.startswith("/"):
            line = line[1:]
        if not line:
            continue
        pats.append(
            _Pattern(
                base_parts=base_parts,
                regex=re.compile(_glob_to_regex(line)),
                negated=negated,
                dir_only=dir_only,
                anchored=anchored,
            )
        )
    return pats


def _glob_to_regex(pat: str) -> str:
    out: list[str] = []
    i, n = 0, len(pat)
    while i < n:
        c = pat[i]
        if c == "*":
            if i + 1 < n and pat[i + 1] == "*":
                prev_ok = i == 0 or pat[i - 1] == "/"
                next_ok = i + 2 == n or pat[i + 2] == "/"
                if prev_ok and i + 2 < n and pat[i + 2] == "/":
                    out.append("(?:[^/]+/)*")
                    i += 3
                    continue
                if prev_ok and next_ok:
                    out.append(".*")
                    i += 2
                    continue
                out.append("[^/]*")
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
            if j >= n:
                out.append(re.escape(c))
            else:
                inner = pat[i + 1 : j]
                if inner.startswith("!"):
                    inner = "^" + inner[1:]
                elif inner.startswith("^"):
                    inner = "\\" + inner
                if inner.startswith("]"):
                    inner = "\\" + inner
                out.append("[" + inner + "]")
                i = j
        else:
            out.append(re.escape(c))
        i += 1
    return "".join(out)
