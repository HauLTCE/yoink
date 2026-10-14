"""Regex-driven import graph for non-Python languages."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, NamedTuple

from yoink.lang import LangSpec
from yoink.lang.resolve import build_namespace_map, resolve_import
from yoink.model import ImportEdge, ModuleGraph, ModuleInfo, Unresolved
from yoink.util import read_text


def _strip_comments(text: str, comment_res: tuple[str, ...]) -> str:
    for pat in comment_res:
        flags = re.MULTILINE | re.DOTALL
        text = re.sub(pat, "", text, flags=flags)
    return text


class _Hit(NamedTuple):
    mod: str          # raw import text
    start: int        # pos where mod text starts (for lineno)
    lead: str         # text of the match before the mod group (kind detection)


def _import_hits(clean: str, spec: LangSpec) -> Iterator[_Hit]:
    """Yield raw-import hits, lang-aware."""
    if spec.id == "go":
        # quoted strings are imports only inside `import (...)` blocks / after `import`
        for bm in re.finditer(r"\bimport\s*\((?P<body>[^)]*)\)", clean, re.DOTALL):
            body, bstart = bm.group("body"), bm.start("body")
            for qm in re.finditer(r'"(?P<mod>[^"]+)"', body):
                lead = body[max(0, qm.start() - 12):qm.start()]
                yield _Hit(qm.group("mod"), bstart + qm.start(), "import(" + lead)
        for sm in re.finditer(
            r'\bimport\s+(?:[._]\s+|\w+\s+)?"(?P<mod>[^"]+)"', clean
        ):
            yield _Hit(sm.group("mod"), sm.start("mod"), clean[sm.start():sm.start("mod")])
        return
    for pat in spec.import_re:
        for m in re.finditer(pat, clean):
            yield _Hit(m.group("mod"), m.start("mod"), clean[m.start():m.start("mod")])


def _classify_kind(spec: LangSpec, lead: str, raw: str) -> str:
    if spec.id == "jsts":
        if re.search(r"\bimport\s+type\b", lead):
            return "type_checking"
        if re.search(r"\bimport\s*\(\s*['\"]?$", lead):
            return "dynamic"
        return "static"
    if spec.id == "ruby" and re.search(r"\bload\s*['\"]?\s*$", lead):
        return "dynamic"
    return "static"


def build_generic_graph(
    root: Path,
    mods: dict[str, ModuleInfo],
    spec: LangSpec,
    source_root: Path,
) -> ModuleGraph:
    """Build a file-granular ModuleGraph from regex import scans."""
    g = ModuleGraph(language=spec.id, modules=mods)
    ns_map = build_namespace_map(mods, spec)
    for name, info in mods.items():
        try:
            text = read_text(info.path)
        except OSError:
            continue
        clean = _strip_comments(text, spec.comment_res)
        for hit in _import_hits(clean, spec):
            raw = hit.mod
            if raw is None:
                continue
            raw = raw.strip()
            if not raw:
                continue
            lineno = clean[: hit.start].count("\n") + 1
            kind = _classify_kind(spec, hit.lead, raw)
            if kind == "dynamic" and spec.id == "ruby":
                # `load` is always dynamic-unresolved, literal or not
                g.unresolved.append(
                    Unresolved(
                        file=name,
                        lineno=lineno,
                        name=raw,
                        kind="dynamic_import",
                        detail="load is dynamic in text mode",
                    )
                )
                continue
            resolved = resolve_import(mods, spec, name, raw, ns_map)
            module_field = resolved if resolved is not None else raw
            g.imports.append(
                ImportEdge(
                    importer=name,
                    module=module_field,
                    kind=kind,
                    lineno=lineno,
                )
            )
        # non-literal dynamic forms -> unresolved
        if spec.id == "jsts":
            for vm in re.finditer(r"\bimport\s*\(\s*(?!['\"])([^)\s]+)", clean):
                g.unresolved.append(
                    Unresolved(file=name, lineno=clean[: vm.start()].count("\n") + 1,
                               name=vm.group(1), kind="dynamic_import",
                               detail="non-literal dynamic import()"))
        if spec.id == "php":
            for vm in re.finditer(
                r"\b(?:require|include)(?:_once)?\s*\(?\s*(?!['\"])([^)\s;]+)", clean,
            ):
                g.unresolved.append(
                    Unresolved(file=name, lineno=clean[: vm.start()].count("\n") + 1,
                               name=vm.group(1), kind="dynamic_import",
                               detail="variable require/include"))
        if spec.id == "ruby":
            for vm in re.finditer(r"\bload\s+(?!['\"])(\S+)", clean):
                g.unresolved.append(
                    Unresolved(file=name, lineno=clean[: vm.start()].count("\n") + 1,
                               name=vm.group(1), kind="dynamic_import",
                               detail="load with non-literal"))
        if spec.id == "cpp":
            for vm in re.finditer(r"#\s*include\s+(?![<\"])(\S+)", clean):
                g.unresolved.append(
                    Unresolved(file=name, lineno=clean[: vm.start()].count("\n") + 1,
                               name=vm.group(1), kind="dynamic_import",
                               detail="macro include"))
    return g
