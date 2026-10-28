"""Graph dispatch + target resolution across Python and 14 non-Python languages."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path, PurePosixPath

from yoink.errors import SymbolNotFoundError
from yoink.gitignore import load_ignore
from yoink.lang import get_spec
from yoink.lang.resolve import find_symbol_candidates
from yoink.model import ModuleGraph, ModuleInfo

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


def build_graph(
    root: Path,
    language: str,
    mods: dict[str, ModuleInfo],
    ignored: Callable[[Path, bool], bool] | None = None,
) -> ModuleGraph:
    """Dispatch graph construction to `build_python_graph` or `build_generic_graph`."""
    root = Path(root).resolve()
    if ignored is None:
        ignored = load_ignore(root)
    if language == "python":
        from yoink.graph.python_ast import build_python_graph

        return build_python_graph(root, mods)

    spec = get_spec(language)
    if spec is None:
        return ModuleGraph(language=language, modules=dict(mods))
    from yoink.graph.generic import build_generic_graph

    return build_generic_graph(root, spec, mods)


def _match_module_key(mods: dict[str, ModuleInfo], raw_mod: str) -> str | None:
    """Match a user-supplied module name or relative file path against `mods`."""
    if raw_mod in mods:
        return raw_mod
    norm = raw_mod.replace("\\", "/").lstrip("./")
    if norm in mods:
        return norm
    no_ext = PurePosixPath(norm).with_suffix("").as_posix()
    if no_ext in mods:
        return no_ext
    dotted = no_ext.replace("/", ".")
    if dotted in mods:
        return dotted
    rust_path = f"crate::{no_ext.replace('/', '::')}"
    if rust_path in mods:
        return rust_path

    suffix_hits = [
        m
        for m, info in mods.items()
        if info.path.as_posix().endswith("/" + norm)
        or info.path.name == norm
        or info.path.stem == norm
        or m.endswith("." + dotted)
        or m.endswith("::" + norm)
    ]
    if len(suffix_hits) == 1:
        return suffix_hits[0]
    return None


def resolve_target(
    mods: dict[str, ModuleInfo],
    graph: ModuleGraph,
    raw_target: str,
    language: str,
) -> tuple[str | None, str | None]:
    """Resolve user `--grab` target into `(module_name, symbol_name)`."""
    if not raw_target or not raw_target.strip():
        if len(mods) == 1:
            return next(iter(mods.keys())), None
        raise SymbolNotFoundError("<empty>")

    target = raw_target.strip()
    spec = get_spec(language)

    if ":" in target and not target.startswith("crate::") and "::" not in target:
        mod_part, sym_part = target.rsplit(":", 1)
        matched_mod = _match_module_key(mods, mod_part)
        if matched_mod is None:
            raise SymbolNotFoundError(target)
        if not sym_part:
            return matched_mod, None
        mod_defns = graph.defns.get(matched_mod, [])
        if any(d.name == sym_part for d in mod_defns):
            if all(d.kind == "import" for d in mod_defns if d.name == sym_part):
                chased = _follow_reexport(graph.defns, [matched_mod], sym_part)
                if chased:
                    return chased, sym_part
            return matched_mod, sym_part
        if language != "python":
            from yoink.util import read_text

            if sym_part in read_text(mods[matched_mod].path):
                return matched_mod, sym_part
        raise SymbolNotFoundError(target)

    matched_mod = _match_module_key(mods, target)
    if matched_mod is not None:
        return matched_mod, None

    for sep in ("::", "."):
        if sep in target:
            mod_part, sym_part = target.rsplit(sep, 1)
            matched_mod = _match_module_key(mods, mod_part)
            if matched_mod is not None:
                mod_defns = graph.defns.get(matched_mod, [])
                if any(d.name == sym_part for d in mod_defns):
                    return matched_mod, sym_part

    cands = find_symbol_candidates(mods, graph, target, spec)
    if len(cands) == 1:
        return cands[0], target
    if len(cands) > 1:
        real_defs = [
            m
            for m in cands
            if any(d.name == target and d.kind != "import" for d in graph.defns.get(m, []))
        ]
        if len(real_defs) == 1:
            return real_defs[0], target
        raise SymbolNotFoundError(target, candidates=cands)

    raise SymbolNotFoundError(target)
