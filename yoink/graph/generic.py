"""Multi-language dependency & symbol graph builder across 14 non-Python ecosystems."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, NamedTuple

from yoink.lang import LangSpec
from yoink.model import Defn, ImportEdge, ModuleGraph, ModuleInfo, SymbolEdge
from yoink.util import read_text


class _Hit(NamedTuple):
    mod: str
    start: int
    lead: str
    names: tuple[tuple[str, str | None], ...] = ()
    kind: str = "static"


def _strip_comments(text: str, comment_res: tuple[str, ...]) -> str:
    """Strip single-line and multi-line comments while preserving exact line numbers (`\n`)
    and never stripping `//` or `/*` inside string literals."""
    n = len(text)
    out = list(text)
    i = 0
    has_hash = any(r.startswith("#") for r in comment_res)
    has_slash = any(r.startswith("//") or r.startswith(r"/\*") for r in comment_res)
    has_lua = any(r.startswith("--") for r in comment_res)
    has_ruby_block = any("=begin" in r for r in comment_res)

    while i < n:
        c = text[i]
        if c in ('"', "'", "`"):
            quote = c
            i += 1
            while i < n:
                if text[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue

        if has_ruby_block and c == "=" and (i == 0 or text[i - 1] == "\n") and text.startswith("=begin", i):
            end_idx = text.find("=end", i + 6)
            limit = (end_idx + 4) if end_idx != -1 else n
            for k in range(i, min(limit, n)):
                if out[k] != "\n":
                    out[k] = " "
            i = limit
            continue

        if has_lua and c == "-" and i + 1 < n and text[i + 1] == "-":
            if i + 3 < n and text[i + 2] == "[" and text[i + 3] == "[":
                end_idx = text.find("]]", i + 4)
                limit = (end_idx + 2) if end_idx != -1 else n
                for k in range(i, min(limit, n)):
                    if out[k] != "\n":
                        out[k] = " "
                i = limit
                continue
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
            continue

        if has_slash and c == "/" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "/":
                while i < n and text[i] != "\n":
                    out[i] = " "
                    i += 1
                continue
            if nxt == "*":
                end_idx = text.find("*/", i + 2)
                limit = (end_idx + 2) if end_idx != -1 else n
                for k in range(i, min(limit, n)):
                    if out[k] != "\n":
                        out[k] = " "
                i = limit
                continue

        if has_hash and c == "#":
            if i + 1 < n and text[i + 1] == "[":
                i += 1
                continue
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
            continue

        i += 1

    return "".join(out)


def _expand_grouped_imports(raw_mod: str, lang_id: str) -> list[tuple[str, tuple[tuple[str, str | None], ...]]]:
    """Expand grouped/brace imports (Rust, PHP, Scala, Elixir) into individual import paths."""
    raw = raw_mod.strip()
    if "{" not in raw or "}" not in raw:
        return [(raw, ())]

    if lang_id == "rust":
        m = re.match(r"^([A-Za-z0-9_:]+)::\{([\s\S]+)\}$", raw)
        if m:
            prefix = m.group(1)
            inner = m.group(2)
            results: list[tuple[str, tuple[tuple[str, str | None], ...]]] = []
            for item in inner.split(","):
                part = item.strip()
                if not part:
                    continue
                if part == "self":
                    results.append((prefix, ()))
                else:
                    sub = part.split(" as ")[0].strip()
                    alias = part.split(" as ")[1].strip() if " as " in part else None
                    results.append((f"{prefix}::{sub}", ((sub.split("::")[-1], alias),)))
            return results

    if lang_id == "php":
        m = re.match(r"^([A-Za-z0-9_\\]+)\\\{([\s\S]+)\}$", raw)
        if m:
            prefix = m.group(1).strip("\\")
            inner = m.group(2)
            results = []
            for item in inner.split(","):
                part = item.strip()
                if not part:
                    continue
                sub = re.split(r"\s+as\s+", part, flags=re.IGNORECASE)[0].strip()
                results.append((f"{prefix}\\{sub}", ()))
            return results

    if lang_id == "scala":
        m = re.match(r"^([A-Za-z0-9_.]+)\.\{([\s\S]+)\}$", raw)
        if m:
            prefix = m.group(1)
            inner = m.group(2)
            results = []
            for item in inner.split(","):
                part = item.strip()
                if not part:
                    continue
                if part in ("_", "*"):
                    results.append((f"{prefix}.*", ()))
                else:
                    sub = re.split(r"\s*(?:=>|as)\s*", part)[0].strip()
                    results.append((f"{prefix}.{sub}", ()))
            return results

    if lang_id == "elixir":
        m = re.match(r"^([A-Za-z0-9_.]+)\.\{([\s\S]+)\}$", raw)
        if m:
            prefix = m.group(1)
            inner = m.group(2)
            return [
                (f"{prefix}.{item.strip()}", ())
                for item in inner.split(",")
                if item.strip()
            ]

    return [(raw, ())]


_GO_IMPORT_BLOCK_RE = re.compile(r"\bimport\s*\(([\s\S]*?)\)", re.MULTILINE)
_GO_IMPORT_LINE_RE = re.compile(r"""(?:[A-Za-z0-9_.]+\s+)?["`]([^"`]+)["`]""")


def _import_hits(clean: str, spec: LangSpec) -> Iterator[_Hit]:
    """Yield matched import edges from comment-stripped source text."""
    if spec.id == "go":
        for blk in _GO_IMPORT_BLOCK_RE.finditer(clean):
            block_start = blk.start()
            body = blk.group(1)
            for m in _GO_IMPORT_LINE_RE.finditer(body):
                yield _Hit(
                    mod=m.group(1),
                    start=block_start + m.start(),
                    lead=m.group(0),
                )

    for rx in spec.import_res:
        for m in rx.finditer(clean):
            groups = [g for g in m.groups() if g is not None]
            if not groups:
                continue
            raw_mod = groups[-1].strip()
            for expanded_mod, names in _expand_grouped_imports(raw_mod, spec.id):
                yield _Hit(
                    mod=expanded_mod,
                    start=m.start(),
                    lead=m.group(0),
                    names=names,
                    kind="static",
                )

    for rx in spec.dynamic_import_res:
        for m in rx.finditer(clean):
            groups = [g for g in m.groups() if g is not None]
            if not groups:
                continue
            yield _Hit(
                mod=groups[-1].strip(),
                start=m.start(),
                lead=m.group(0),
                kind="dynamic",
            )


_DEFN_PATTERNS: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    "jsts": (
        ("func", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s+([A-Za-z_$][A-Za-z0-9_$]*)", re.MULTILINE)),
        ("class", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][A-Za-z0-9_$]*)", re.MULTILINE)),
        ("interface", re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][A-Za-z0-9_$]*)", re.MULTILINE)),
        ("type", re.compile(r"^\s*(?:export\s+)?type\s+([A-Za-z_$][A-Za-z0-9_$]*)\b", re.MULTILINE)),
        ("enum", re.compile(r"^\s*(?:export\s+)?(?:const\s+)?enum\s+([A-Za-z_$][A-Za-z0-9_$]*)", re.MULTILINE)),
        ("assign", re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*(?::[^=]+)?=", re.MULTILINE)),
    ),
    "go": (
        ("func", re.compile(r"^func\s+(?:\([^)]+\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[[^\]]+\])?\s*\(", re.MULTILINE)),
        ("type", re.compile(r"^type\s+([A-Za-z_][A-Za-z0-9_]*)\b", re.MULTILINE)),
        ("assign", re.compile(r"^(?:var|const)\s+([A-Za-z_][A-Za-z0-9_]*)\b", re.MULTILINE)),
    ),
    "rust": (
        ("func", re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:const\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
        ("struct", re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?struct\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
        ("enum", re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?enum\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
        ("trait", re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:unsafe\s+)?trait\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
        ("type", re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?type\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
        ("assign", re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:const|static)\s+([A-Za-z_][A-Za-z0-9_]*)\s*:", re.MULTILINE)),
        ("macro", re.compile(r"^\s*macro_rules!\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
    ),
    "cpp": (
        ("class", re.compile(r"^\s*(?:template\s*<[^>]*>\s*)?(?:class|struct)\s+(?:[A-Z0-9_]+\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^{;]+)?\{", re.MULTILINE)),
        ("enum", re.compile(r"^\s*enum\s+(?:class\s+|struct\s+)?([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
        ("func", re.compile(r"^(?:template\s*<[^>]*>\s*)?(?:(?:inline|static|constexpr|extern|virtual|explicit)\s+)*[A-Za-z_][A-Za-z0-9_:<>,*\s&]*?\b([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*(?:const\s*)?(?:noexcept\s*)?\{", re.MULTILINE)),
        ("type", re.compile(r"^\s*using\s+([A-Za-z_][A-Za-z0-9_]*)\s*=", re.MULTILINE)),
    ),
    "csharp": (
        ("class", re.compile(r"^\s*(?:(?:public|internal|private|protected|static|abstract|sealed|partial)\s+)*(?:class|struct|record|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
        ("func", re.compile(r"^\s*(?:(?:public|internal|private|protected|static|virtual|override|async)\s+)+[A-Za-z_][A-Za-z0-9_<>?,\[\]\s]*\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:<[^>]+>)?\s*\(", re.MULTILINE)),
    ),
    "java": (
        ("class", re.compile(r"^\s*(?:(?:public|protected|private|abstract|final|static|sealed|non-sealed)\s+)*(?:class|interface|enum|record|@interface)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
        ("func", re.compile(r"^\s*(?:(?:public|protected|private|static|final|synchronized|abstract)\s+)+(?:<[^>]+>\s+)?[A-Za-z_][A-Za-z0-9_<>\[\],?\s]*\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.MULTILINE)),
    ),
    "php": (
        ("class", re.compile(r"^\s*(?:(?:abstract|final|readonly)\s+)*(?:class|interface|trait|enum)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
        ("func", re.compile(r"^\s*(?:(?:public|protected|private|static|abstract|final)\s+)*function\s+&?([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
    ),
    "ruby": (
        ("class", re.compile(r"^\s*(?:class|module)\s+([A-Za-z_][A-Za-z0-9_:]*)", re.MULTILINE)),
        ("func", re.compile(r"^\s*def\s+(?:self\.)?([A-Za-z_][A-Za-z0-9_?!]*)", re.MULTILINE)),
    ),
    "kotlin": (
        ("class", re.compile(r"^\s*(?:(?:public|internal|private|protected|abstract|open|data|sealed|value|enum|annotation)\s+)*(?:class|interface|object)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
        ("func", re.compile(r"^\s*(?:(?:public|internal|private|protected|suspend|inline|operator|infix|tailrec|override|open)\s+)*fun\s+(?:<[^>]+>\s*)?(?:[A-Za-z0-9_.<>?]+\.)?([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
        ("type", re.compile(r"^\s*(?:public|internal|private)?\s*typealias\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
        ("assign", re.compile(r"^\s*(?:(?:public|internal|private|const)\s+)*(?:val|var)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
    ),
    "swift": (
        ("class", re.compile(r"^\s*(?:(?:public|internal|private|fileprivate|open|final|indirect)\s+)*(?:struct|class|enum|protocol|actor)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
        ("func", re.compile(r"^\s*(?:(?:public|internal|private|fileprivate|open|static|class|mutating)\s+)*func\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
        ("type", re.compile(r"^\s*(?:(?:public|internal|private|fileprivate)\s+)*typealias\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
    ),
    "dart": (
        ("class", re.compile(r"^\s*(?:(?:abstract|base|interface|final|sealed|mixin)\s+)*(?:class|mixin|enum|extension)\s+([A-Za-z_$][A-Za-z0-9_$]*)", re.MULTILINE)),
        ("type", re.compile(r"^\s*typedef\s+([A-Za-z_$][A-Za-z0-9_$]*)", re.MULTILINE)),
        ("func", re.compile(r"^(?:[A-Za-z_$][A-Za-z0-9_$<>?\s]*\s+)?([A-Za-z_$][A-Za-z0-9_$]*)\s*(?:<[^>]+>)?\s*\([^;]*\)\s*(?:async\*?\s*)?(?:\{|=>)", re.MULTILINE)),
    ),
    "scala": (
        ("class", re.compile(r"^\s*(?:(?:final|sealed|abstract|case|implicit|open|lazy)\s+)*(?:class|trait|object|enum)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
        ("func", re.compile(r"^\s*(?:(?:override|private|protected|final|implicit|inline)\s+)*def\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
        ("type", re.compile(r"^\s*(?:opaque\s+)?type\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
    ),
    "lua": (
        ("func", re.compile(r"^\s*(?:local\s+)?function\s+(?:[A-Za-z_][A-Za-z0-9_]*[.:])?([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)),
        ("assign", re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.]*)\s*=\s*function\s*\(", re.MULTILINE)),
    ),
    "elixir": (
        ("class", re.compile(r"^\s*defmodule\s+([A-Za-z_][A-Za-z0-9_.]*)\s+do\b", re.MULTILINE)),
        ("func", re.compile(r"^\s*(?:def|defp|defmacro|defmacrop|defguard)\s+([A-Za-z_][A-Za-z0-9_?!]*)", re.MULTILINE)),
    ),
}

_CONTROL_KEYWORDS = frozenset({
    "if", "else", "for", "while", "switch", "case", "return", "catch", "try",
    "sizeof", "typeof", "delete", "new", "throw", "await", "yield",
})


def _find_block_end_line(clean: str, start_idx: int, lang_id: str) -> int:
    """Compute the ending 1-based line number of a brace or `end`-delimited definition."""
    lines_before = clean.count("\n", 0, start_idx) + 1
    if lang_id in ("ruby", "lua", "elixir"):
        rest = clean[start_idx:]
        depth = 0
        line_offset = 0
        for line in rest.splitlines():
            opens = len(re.findall(r"\b(?:def|defp|defmacro|defmodule|class|module|function|do|if|case|unless)\b", line))
            closes = len(re.findall(r"\bend\b", line))
            depth += opens - closes
            if depth <= 0 and line_offset > 0:
                return lines_before + line_offset
            line_offset += 1
        return lines_before + max(line_offset - 1, 0)

    n = len(clean)
    i = start_idx
    depth = 0
    saw_open = False
    while i < n:
        c = clean[i]
        if c == "{":
            depth += 1
            saw_open = True
        elif c == "}":
            depth -= 1
            if saw_open and depth <= 0:
                return clean.count("\n", 0, i) + 1
        elif c == ";" and not saw_open:
            return clean.count("\n", 0, i) + 1
        i += 1
    return clean.count("\n") + 1


def extract_generic_defns(clean: str, lang_id: str) -> list[Defn]:
    """Extract top-level symbol definitions and their line spans for `lang_id`."""
    patterns = _DEFN_PATTERNS.get(lang_id, ())
    defns: list[Defn] = []
    seen: set[tuple[str, int]] = set()
    for kind, rx in patterns:
        for m in rx.finditer(clean):
            name = m.group(1).split(".")[-1].split("::")[-1]
            if name in _CONTROL_KEYWORDS:
                continue
            lineno = clean.count("\n", 0, m.start()) + 1
            if (name, lineno) in seen:
                continue
            seen.add((name, lineno))
            end_lineno = _find_block_end_line(clean, m.start(), lang_id)
            defns.append(
                Defn(
                    name=name,
                    kind=kind,
                    lineno=lineno,
                    end_lineno=max(lineno, end_lineno),
                )
            )
    defns.sort(key=lambda d: (d.lineno, d.name))
    return defns


_IDENT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")


def build_generic_graph(
    root: Path,
    spec: LangSpec,
    mods: dict[str, ModuleInfo],
) -> ModuleGraph:
    """Build dependency and symbol graph across non-Python source files."""
    graph = ModuleGraph(language=spec.id, modules=dict(mods))
    cleaned_texts: dict[str, str] = {}

    for mod_name, info in sorted(mods.items()):
        raw_text = read_text(info.path)
        clean = _strip_comments(raw_text, spec.comment_res)
        cleaned_texts[mod_name] = clean

        for hit in _import_hits(clean, spec):
            lineno = clean.count("\n", 0, hit.start) + 1
            graph.imports.append(
                ImportEdge(
                    importer=mod_name,
                    module=hit.mod,
                    names=hit.names,
                    level=0,
                    kind=hit.kind,
                    lineno=lineno,
                )
            )

        defns = extract_generic_defns(clean, spec.id)
        graph.defns[mod_name] = defns

    pkg_sym_owners: dict[tuple[str | None, str], list[str]] = {}
    global_sym_owners: dict[str, list[str]] = {}
    for mod_name, defns in graph.defns.items():
        pkg = mods[mod_name].package
        for d in defns:
            pkg_sym_owners.setdefault((pkg, d.name), []).append(mod_name)
            global_sym_owners.setdefault(d.name, []).append(mod_name)

    for mod_name, clean in cleaned_texts.items():
        info = mods[mod_name]
        own_names = {d.name for d in graph.defns.get(mod_name, ())}
        referenced_idents = set(_IDENT_RE.findall(clean)) - own_names - _CONTROL_KEYWORDS
        for ident in sorted(referenced_idents):
            if ident in global_sym_owners:
                graph.symbols.append(SymbolEdge(module=mod_name, name=ident, lineno=1))
            if spec.id in ("go", "java", "kotlin", "scala", "csharp", "swift"):
                for target_mod in pkg_sym_owners.get((info.package, ident), ()):
                    if target_mod != mod_name:
                        graph.imports.append(
                            ImportEdge(
                                importer=mod_name,
                                module=target_mod,
                                names=((ident, None),),
                                level=0,
                                kind="implicit",
                                lineno=1,
                            )
                        )

    return graph
