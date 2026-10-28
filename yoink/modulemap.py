"""Maps source paths to module dotted names for Python repositories."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from yoink.gitignore import iter_files, load_ignore
from yoink.model import ModuleInfo
from yoink.util import find_source_root


def build_module_map(
    root: Path,
    ignored: Callable[[Path, bool], bool] | None = None,
) -> dict[str, ModuleInfo]:
    """Build module map for all `.py`/`.pyi` files under `root`."""
    root = Path(root).resolve()
    if ignored is None:
        ignored = load_ignore(root)
    source_root = find_source_root(root, language="python")

    # If `source_root` itself is a Python package directory (contains `__init__.py`),
    # preserve its package name prefix so internal files like `types.py` or `io.py`
    # are indexed as `<pkg>.types` and `<pkg>.io` rather than shadowing stdlib `types`/`io`.
    pkg_prefix_root = (
        source_root.parent
        if (source_root / "__init__.py").is_file() or (source_root / "__init__.pyi").is_file()
        else source_root
    )

    mods: dict[str, ModuleInfo] = {}
    for path in iter_files(root, ignored):
        if path.suffix not in (".py", ".pyi"):
            continue
        try:
            rel = path.resolve().relative_to(pkg_prefix_root)
        except ValueError:
            rel = path.resolve().relative_to(root)

        parts = list(rel.with_suffix("").parts)
        if not parts:
            continue

        is_pkg_init = parts[-1] == "__init__"
        if is_pkg_init:
            if len(parts) == 1:
                mod_name = "__init__"
                pkg = None
            else:
                mod_name = ".".join(parts[:-1])
                pkg = mod_name
        else:
            mod_name = ".".join(parts)
            pkg = ".".join(parts[:-1]) if len(parts) > 1 else None

        info = ModuleInfo(
            name=mod_name,
            path=path.resolve(),
            package=pkg,
            is_pkg_init=is_pkg_init,
        )
        if mod_name not in mods or path.suffix == ".py":
            mods[mod_name] = info

    return mods
