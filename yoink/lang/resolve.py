"""Generic symbol/import resolution for non-Python languages."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

from yoink.lang import LangSpec
from yoink.model import ModuleInfo
from yoink.util import read_text


def _read(path: Path) -> str:
    try:
        return read_text(path)
    except OSError:
        return ""


def _stem(path_str: str) -> str:
    return PurePosixPath(path_str).stem


def _noext(p: str) -> str:
    pp = PurePosixPath(p)
    if "." in pp.name:
        return str(pp.with_suffix(""))
    return str(pp)


def _join(base: str, rel: str) -> str:
    parts = PurePosixPath(base + "/" + rel).parts
    out: list[str] = []
    for p in parts:
        if p == "..":
            if out:
                out.pop()
        elif p == ".":
            continue
        else:
            out.append(p)
    return "/".join(out)


def find_symbol_candidates(
    root: Path,
    mods: dict[str, ModuleInfo],
    spec: LangSpec,
    symbol: str,
) -> list[tuple[str, int]]:
    """Score in-repo modules for a bare symbol: defn hit 100 > stem 60 > content 10."""
    results: dict[str, int] = {}
    pats = [
        re.compile(p.replace("{sym}", re.escape(symbol)))
        for p in spec.defn_res
    ]
    for name, info in mods.items():
        text = _read(info.path)
        if not text:
            continue
        score = 0
        for pat in pats:
            if pat.search(text):
                score = 100
                break
        if score == 0:
            if _stem(info.path.name) == symbol:
                score = 60
            elif symbol in text:
                score = 10
        if score:
            results[name] = score
    return sorted(results.items(), key=lambda kv: (-kv[1], kv[0]))


def build_namespace_map(
    mods: dict[str, ModuleInfo], spec: LangSpec
) -> dict[str, str]:
    """namespace/package decl -> module name (csharp/java/php/go/cpp)."""
    out: dict[str, str] = {}
    if not spec.namespace_re:
        return out
    rx = re.compile(spec.namespace_re)
    for name, info in mods.items():
        text = _read(info.path)
        if not text:
            continue
        m = rx.search(text)
        if m:
            ns = m.group("ns").strip().rstrip(";")
            out.setdefault(ns, name)
    return out


def _mods_root(mods: dict[str, ModuleInfo]) -> Path | None:
    if not mods:
        return None
    paths = [info.path for info in mods.values()]
    common = paths[0].parent
    for p in paths[1:]:
        while not p.is_relative_to(common):
            if common.parent == common:
                break
            common = common.parent
    return common


def _composer_psr4(root: Path) -> dict[str, str]:
    cj = root / "composer.json"
    if not cj.is_file():
        return {}
    try:
        data = json.loads(_read(cj))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, str] = {}
    auto = data.get("autoload") if isinstance(data, dict) else None
    if isinstance(auto, dict):
        psr4 = auto.get("psr-4")
        if isinstance(psr4, dict):
            for prefix, dpath in psr4.items():
                if isinstance(prefix, str) and isinstance(dpath, str):
                    out[prefix.rstrip("\\") + "\\"] = dpath.rstrip("/") + "/"
    return out


def _match_path(mods: dict[str, ModuleInfo], candidate: str) -> str | None:
    """Match a repo-relative-ish path (with or without ext) to a module name."""
    cand = _noext(candidate.replace("\\", "/"))
    if cand in mods:
        return cand
    for name in mods:
        if name.endswith("/" + cand):
            return name
    base = PurePosixPath(cand).name
    for name in mods:
        if PurePosixPath(name).name == base:
            return name
    return None


def resolve_import(
    mods: dict[str, ModuleInfo],
    spec: LangSpec,
    importer: str,
    raw: str,
    ns_map: dict[str, str] | None = None,
) -> str | None:
    """Map a raw import string to an in-repo module name, or None."""
    raw = raw.strip()
    if not raw:
        return None
    ns_map = ns_map or {}
    lang = spec.id

    if _is_stdlib(spec, raw):
        return None

    if lang == "csharp":
        return _resolve_csharp(mods, raw, ns_map)
    if lang == "jsts":
        return _resolve_jsts(mods, importer, raw, spec)
    if lang == "go":
        return _resolve_go(mods, raw)
    if lang == "rust":
        return _resolve_rust(mods, importer, raw)
    if lang == "java":
        return _resolve_java(mods, raw, ns_map)
    if lang == "cpp":
        return _resolve_cpp(mods, importer, raw)
    if lang == "ruby":
        return _resolve_ruby(mods, importer, raw)
    if lang == "php":
        return _resolve_php(mods, importer, raw, ns_map)
    return None


def _is_stdlib(spec: LangSpec, raw: str) -> bool:
    first = re.split(r"[./:\\]", raw, maxsplit=1)[0]
    if first in spec.stdlib_names:
        return True
    for p in spec.stdlib_prefixes:
        if raw == p or raw.startswith(p):
            return True
    return False


def _resolve_csharp(
    mods: dict[str, ModuleInfo], raw: str, ns_map: dict[str, str]
) -> str | None:
    raw = raw.split("=")[-1].strip().rstrip(";").strip()
    if raw in ns_map:
        return ns_map[raw]
    # try longest ns prefix -> file in that namespace dir, else leaf match
    parts = raw.split(".")
    for i in range(len(parts), 0, -1):
        ns = ".".join(parts[:i])
        if ns in ns_map:
            rest = parts[i:]
            if not rest:
                return ns_map[ns]
            hit = _match_path(mods, "/".join(rest))
            return hit or ns_map[ns]
    return _match_path(mods, raw.replace(".", "/"))


def _resolve_jsts(
    mods: dict[str, ModuleInfo], importer: str, raw: str, spec: LangSpec
) -> str | None:
    if raw.startswith("node:"):
        return None
    if not raw.startswith("."):
        return None
    base = str(PurePosixPath(importer).parent)
    norm = _join(base, raw)
    if norm in mods:
        return norm
    for e in spec.extensions:
        if norm + e in mods:
            return norm + e
        # raw may carry its own ext already
        noext = _noext(norm)
        if noext in mods:
            return noext
    for e in spec.extensions:
        if norm + "/index" + e in mods:
            return norm + "/index" + e
    return _match_path(mods, norm)


def _resolve_go(mods: dict[str, ModuleInfo], raw: str) -> str | None:
    last = raw.split("/")[-1]
    for name in mods:
        if PurePosixPath(name).parent.name == last:
            return name
    for name in mods:
        if name.endswith("/" + last) or name == last:
            return name
    return None


def _crate_root(mods: dict[str, ModuleInfo]) -> str:
    """Dir holding main.rs/lib.rs, else ''."""
    for name in mods:
        n = PurePosixPath(name).name
        if n in ("main", "lib"):
            return str(PurePosixPath(name).parent)
    return ""


def _rust_use_to_mod(mods: dict[str, ModuleInfo], anchor: str, segs: list[str]) -> str | None:
    """use-path segments -> module: try full, then drop trailing item segs."""
    for k in range(len(segs), 0, -1):
        sub = "/".join(segs[:k])
        cand = _join(anchor, sub) if anchor else sub
        for c in (cand, cand + "/mod"):
            if c in mods:
                return c
        hit = _match_path(mods, cand)
        if hit:
            return hit
    return None


def _resolve_rust(
    mods: dict[str, ModuleInfo], importer: str, raw: str
) -> str | None:
    base = str(PurePosixPath(importer).parent)
    if "::" not in raw:
        # `mod foo;` -> sibling foo.rs or foo/mod.rs
        for c in (_join(base, raw), _join(base, raw + "/mod")):
            if c in mods:
                return c
        return _match_path(mods, _join(base, raw))
    segs = raw.split("::")
    if segs[0] == "crate":
        anchor = _crate_root(mods)
        return _rust_use_to_mod(mods, anchor, segs[1:])
    if segs[0] == "self":
        return _rust_use_to_mod(mods, base, segs[1:])
    if segs[0] == "super":
        ups = 0
        i = 0
        while i < len(segs) and segs[i] == "super":
            ups += 1
            i += 1
        anchor = base
        for _ in range(ups):
            anchor = str(PurePosixPath(anchor).parent)
            if anchor == ".":
                anchor = ""
        return _rust_use_to_mod(mods, anchor, segs[i:])
    # use <ext>::thing -> external crate
    return None


def _resolve_java(
    mods: dict[str, ModuleInfo], raw: str, ns_map: dict[str, str]
) -> str | None:
    return _match_path(mods, raw.replace(".", "/"))


def _resolve_cpp(
    mods: dict[str, ModuleInfo], importer: str, raw: str
) -> str | None:
    base = str(PurePosixPath(importer).parent)
    rel = _join(base, raw)
    if rel in mods:
        return rel
    hit = _match_path(mods, rel)
    if hit:
        return hit
    return _match_path(mods, raw)


def _resolve_ruby(
    mods: dict[str, ModuleInfo], importer: str, raw: str
) -> str | None:
    base = str(PurePosixPath(importer).parent)
    raw = raw.strip("'\"")
    rel = _join(base, raw)
    for c in (rel, rel + ".rb"):
        if c in mods:
            return c
    return _match_path(mods, rel)


def _resolve_php(
    mods: dict[str, ModuleInfo], importer: str, raw: str, ns_map: dict[str, str]
) -> str | None:
    raw = re.sub(r"\s+as\s+\w+$", "", raw.strip(), flags=re.IGNORECASE)
    if "\\" in raw:
        # namespace-style `use Foo\Bar` -> ns_map / PSR-4 / path
        if raw in ns_map:
            return ns_map[raw]
        path = raw.replace("\\", "/")
        root = _mods_root(mods)
        if root is not None:
            psr4 = _composer_psr4(root)
            for prefix in sorted(psr4, key=len, reverse=True):
                pfx = prefix.rstrip("\\")
                if raw == pfx or raw.startswith(prefix):
                    rest = raw[len(prefix):].replace("\\", "/")
                    cand = (psr4[prefix] + rest).strip("/")
                    hit = _match_path(mods, cand)
                    if hit:
                        return hit
        return _match_path(mods, path)
    # require/include 'rel/path.php' -> relative to importer, then root
    base = str(PurePosixPath(importer).parent)
    hit = _match_path(mods, _join(base, raw))
    if hit:
        return hit
    return _match_path(mods, raw)
