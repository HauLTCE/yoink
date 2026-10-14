"""Graph dispatch + target resolution."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path, PurePosixPath

from yoink.errors import SymbolNotFoundError
from yoink.gitignore import iter_files, load_ignore
from yoink.lang import get_spec
from yoink.lang.resolve import _mods_root, find_symbol_candidates
from yoink.model import ModuleGraph, ModuleInfo
from yoink.util import find_source_root

_PKG_INIT_STEMS = {"__init__", "index", "mod"}


def _follow_reexport(
    defns: dict[str, list], hits: list[str], target: str
) -> str | None:
    """Chase a re-export-only hit set to the module that really defines target."""
    real = [
        m
        for m, ds in defns.items()
        if m not in hits and any(d.name == target and d.kind != "import" for d in ds)
    ]
    return real[0] if len(real) == 1 else None


def build_generic_module_map(
    root: Path,
    extensions: tuple[str, ...],
    ignored: Callable[[Path, bool], bool] | None = None,
) -> dict[str, ModuleInfo]:
    """ModuleInfo for every file matching extensions: name = posix rel path minus ext."""
    root = Path(root)
    if ignored is None:
        ignored = load_ignore(root)
    source_root = find_source_root(root)
    exts = tuple(e.lower() for e in extensions)
    mods: dict[str, ModuleInfo] = {}
    for f in sorted(p for p in iter_files(source_root, ignored) if p.suffix.lower() in exts):
        rel = f.relative_to(source_root)
        name = rel.with_suffix("").as_posix()
        package = rel.parent.as_posix() or None
        is_pkg_init = f.stem in _PKG_INIT_STEMS
        mods[name] = ModuleInfo(name=name, path=f, package=package, is_pkg_init=is_pkg_init)
    return mods


def build_graph(
    root: Path,
    language: str,
    mods: dict[str, ModuleInfo],
) -> ModuleGraph:
    """Dispatch to python AST or generic regex graph."""
    if language == "python":
        from yoink.graph.python_ast import build_python_graph

        return build_python_graph(root, mods)
    spec = get_spec(language)
    from yoink.graph.generic import build_generic_graph

    return build_generic_graph(Path(root), mods, spec, Path(root))


def resolve_target(
    mods: dict[str, ModuleInfo],
    defns: dict[str, list],
    target: str,
    language: str,
) -> tuple[str | None, str | None]:
    """Parse target into (module, symbol)."""
    target = target.strip()
    if not target:
        raise SymbolNotFoundError(target)

    if language == "python":
        return _resolve_target_python(mods, defns, target)
    return _resolve_target_generic(mods, target, language)


def _resolve_target_python(
    mods: dict[str, ModuleInfo],
    defns: dict[str, list],
    target: str,
) -> tuple[str | None, str | None]:
    if ":" in target:
        mod_name, sym = target.split(":", 1)
        mod_name = mod_name.strip()
        sym = sym.strip()
        if mod_name in mods:
            return mod_name, sym or None
        # try suffix match on dotted name
        for name in mods:
            if name.endswith(mod_name) or name.endswith("." + mod_name):
                return name, sym or None
        raise SymbolNotFoundError(target)
    # bare symbol or module
    # spec order: defn names first, then module names
    hits = [m for m, ds in defns.items() if any(d.name == target for d in ds)]
    if len(hits) > 1:
        # prefer modules that define it for real over re-export bindings
        real = [
            m
            for m in hits
            if any(d.name == target and d.kind != "import" for d in defns[m])
        ]
        if len(real) == 1:
            return real[0], target
        if len(real) > 1:
            raise SymbolNotFoundError(target, candidates=sorted(real))
        # all hits are re-export bindings — chase them to the definer
        resolved = _follow_reexport(defns, hits, target)
        if resolved:
            return resolved, target
        raise SymbolNotFoundError(target, candidates=sorted(hits))
    if len(hits) == 1:
        return hits[0], target
    if target in mods:
        return target, None
    for name in mods:
        if name == target or name.endswith("." + target):
            return name, None
    raise SymbolNotFoundError(target)


def _resolve_target_generic(
    mods: dict[str, ModuleInfo],
    target: str,
    language: str,
) -> tuple[str | None, str | None]:
    if ":" in target:
        anchor, sym = target.split(":", 1)
        anchor = anchor.strip().replace("\\", "/")
        sym = sym.strip()
        # file anchor: strip ext if present
        anchor_noext = anchor.rsplit(".", 1)[0] if "." in PurePosixPath(anchor).name else anchor
        if anchor_noext in mods:
            return anchor_noext, sym or None
        for name in mods:
            if name.endswith("/" + anchor_noext) or name == anchor_noext:
                return name, sym or None
        raise SymbolNotFoundError(target)
    # bare symbol or explicit path
    tgt = target.replace("\\", "/")
    # whole-dir target unsupported
    stripped = tgt.rstrip("/")
    if tgt.endswith("/") or any(info.package == stripped for info in mods.values()):
        raise SymbolNotFoundError(target)
    if tgt in mods:
        return tgt, None
    if tgt.rsplit(".", 1)[0] in mods:
        return tgt.rsplit(".", 1)[0], None
    # find_symbol_candidates scoring
    spec = get_spec(language)
    if not mods:
        raise SymbolNotFoundError(target)
    root = _mods_root(mods) or Path(".")
    cands = find_symbol_candidates(root, mods, spec, tgt)
    if not cands:
        raise SymbolNotFoundError(target)
    top = cands[0][1]
    tops = [n for n, s in cands if s == top]
    if len(tops) > 1:
        raise SymbolNotFoundError(target, candidates=sorted(tops))
    return tops[0], tgt
