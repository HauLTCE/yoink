"""Python module map: filesystem .py files -> dotted canonical names."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from yoink.gitignore import iter_files, load_ignore
from yoink.model import ModuleInfo
from yoink.util import find_source_root


def build_module_map(
    root: Path, ignored: Callable[[Path, bool], bool] | None = None
) -> dict[str, ModuleInfo]:
    """Map dotted module names to ModuleInfo for every .py under the source root.

    Loose files (an ancestor dir under the source root missing __init__.py) get
    canonical ``dir.file`` plus a bare-stem alias ``file`` -> same ModuleInfo
    when the stem is unclaimed; first sorted path wins the alias.
    """
    root = Path(root)
    if ignored is None:
        ignored = load_ignore(root)
    source_root = find_source_root(root)
    files = sorted(p for p in iter_files(source_root, ignored) if p.suffix == ".py")
    mods: dict[str, ModuleInfo] = {}
    loose: list[tuple[str, ModuleInfo]] = []
    for f in files:
        rel = f.relative_to(source_root)
        is_pkg_init = f.name == "__init__.py"
        if is_pkg_init:
            dotted = ".".join(rel.parent.parts)
            package = ".".join(rel.parent.parts[:-1]) or None
        else:
            dotted = ".".join(rel.with_suffix("").parts)
            package = ".".join(rel.parent.parts) or None
        if not dotted:
            continue
        is_loose = _has_loose_ancestor(rel, source_root)
        info = ModuleInfo(name=dotted, path=f, package=package, is_pkg_init=is_pkg_init)
        mods.setdefault(dotted, info)
        if is_loose:
            loose.append((f.stem, info))
    for stem, info in loose:
        mods.setdefault(stem, info)
    return mods


def _has_loose_ancestor(rel: Path, source_root: Path) -> bool:
    for parent in rel.parents[:-1]:
        if not (source_root / parent / "__init__.py").exists():
            return True
    return False
