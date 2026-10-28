"""Multi-language module discovery, manifest-aware namespace mapping, and import resolution."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from yoink.gitignore import iter_files, load_ignore
from yoink.lang import LangSpec
from yoink.model import ModuleGraph, ModuleInfo
from yoink.util import find_source_root, read_text

_DECL_PACKAGE_RE = re.compile(
    r"^\s*package\s+([A-Za-z_][A-Za-z0-9_.]*)\s*;?", re.MULTILINE
)
_DECL_CS_NAMESPACE_RE = re.compile(
    r"^\s*namespace\s+([A-Za-z_][A-Za-z0-9_.]*)\s*(?:;|\{)", re.MULTILINE
)
_DECL_PHP_NAMESPACE_RE = re.compile(
    r"^\s*namespace\s+([A-Za-z_][A-Za-z0-9_\\]*)\s*(?:;|\{)", re.MULTILINE
)
_DECL_ELIXIR_MOD_RE = re.compile(
    r"^\s*defmodule\s+([A-Za-z_][A-Za-z0-9_.]*)\s+do\b", re.MULTILINE
)


def _extract_declared_package(text: str, lang_id: str) -> str | None:
    if lang_id in ("java", "kotlin", "scala", "go"):
        m = _DECL_PACKAGE_RE.search(text)
        return m.group(1) if m else None
    if lang_id == "csharp":
        m = _DECL_CS_NAMESPACE_RE.search(text)
        return m.group(1) if m else None
    if lang_id == "php":
        m = _DECL_PHP_NAMESPACE_RE.search(text)
        return m.group(1).strip("\\") if m else None
    if lang_id == "elixir":
        m = _DECL_ELIXIR_MOD_RE.search(text)
        return m.group(1) if m else None
    return None


def _mods_root(
    root: Path,
    spec: LangSpec,
    ignored: Callable[[Path, bool], bool] | None = None,
) -> dict[str, ModuleInfo]:
    """Discover all source modules for `spec` under `root`."""
    root = Path(root).resolve()
    if ignored is None:
        ignored = load_ignore(root)
    src_root = find_source_root(root, language=spec.id)
    exts = set(spec.extensions)

    mods: dict[str, ModuleInfo] = {}
    for path in iter_files(root, ignored):
        if path.suffix.lower() not in exts:
            continue
        if spec.id == "go" and path.name.endswith("_test.go"):
            continue
        try:
            rel = path.resolve().relative_to(src_root)
        except ValueError:
            rel = path.resolve().relative_to(root)

        rel_posix = rel.as_posix()
        no_ext = rel.with_suffix("").as_posix()
        stem = path.stem

        text = read_text(path)
        decl_pkg = _extract_declared_package(text, spec.id)

        if spec.id in ("java", "kotlin", "scala"):
            if decl_pkg:
                mod_name = f"{decl_pkg}.{stem}"
                pkg = decl_pkg
            else:
                mod_name = no_ext.replace("/", ".")
                pkg = ".".join(mod_name.split(".")[:-1]) or None
            is_init = False
        elif spec.id == "rust":
            if no_ext in ("lib", "main"):
                mod_name = "crate"
                pkg = "crate"
                is_init = True
            elif stem == "mod":
                parent_dotted = rel.parent.as_posix().replace("/", "::")
                mod_name = f"crate::{parent_dotted}" if parent_dotted != "." else "crate"
                pkg = mod_name
                is_init = True
            else:
                dotted = no_ext.replace("/", "::")
                mod_name = f"crate::{dotted}"
                pkg = "crate::" + "::".join(dotted.split("::")[:-1]) if "::" in dotted else "crate"
                is_init = False
        elif spec.id == "jsts":
            mod_name = no_ext
            is_init = stem == "index"
            pkg = rel.parent.as_posix() if str(rel.parent) != "." else None
        elif spec.id == "go":
            mod_name = rel_posix
            pkg = rel.parent.as_posix() if str(rel.parent) != "." else (decl_pkg or "main")
            is_init = False
        elif spec.id in ("csharp", "php", "elixir"):
            mod_name = rel_posix
            pkg = decl_pkg
            is_init = False
        elif spec.id == "swift":
            parts = rel.parts
            pkg = parts[0] if len(parts) > 1 else "main"
            mod_name = rel_posix
            is_init = False
        elif spec.id == "lua":
            mod_name = no_ext.replace("/", ".")
            is_init = stem == "init"
            if is_init and "." in mod_name:
                mod_name = mod_name.rsplit(".", 1)[0]
            pkg = mod_name.rsplit(".", 1)[0] if "." in mod_name else None
        else:
            mod_name = rel_posix
            pkg = rel.parent.as_posix() if str(rel.parent) != "." else None
            is_init = False

        mods[mod_name] = ModuleInfo(
            name=mod_name,
            path=path.resolve(),
            package=pkg,
            is_pkg_init=is_init,
        )
    return mods


def _strip_jsonc_comments(raw: str) -> str:
    """Remove // and /* */ comments and trailing commas from tsconfig.json / jsconfig.json."""
    out: list[str] = []
    i = 0
    n = len(raw)
    in_str = False
    while i < n:
        c = raw[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(raw[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and raw[i + 1] == "/":
            while i < n and raw[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and raw[i + 1] == "*":
            i += 2
            while i + 1 < n and not (raw[i] == "*" and raw[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    cleaned = "".join(out)
    return re.sub(r",\s*([}\]])", r"\1", cleaned)


def build_namespace_map(
    root: Path,
    mods: dict[str, ModuleInfo],
    spec: LangSpec,
) -> dict[str, str]:
    """Map project namespaces, aliases, and manifest prefixes to internal module keys."""
    root = Path(root).resolve()
    ns_map: dict[str, str] = {}

    src_root = find_source_root(root, language=spec.id)
    for mod_key, info in mods.items():
        ns_map[mod_key] = mod_key
        try:
            rel_src = info.path.relative_to(src_root).as_posix()
            ns_map.setdefault(rel_src, mod_key)
            ns_map.setdefault(PurePosixPath(rel_src).with_suffix("").as_posix(), mod_key)
        except ValueError:
            pass
        try:
            rel_root = info.path.relative_to(root).as_posix()
            ns_map.setdefault(rel_root, mod_key)
            ns_map.setdefault(PurePosixPath(rel_root).with_suffix("").as_posix(), mod_key)
        except ValueError:
            pass
        ns_map.setdefault(info.path.name, mod_key)
        ns_map.setdefault(info.path.stem, mod_key)
        if info.package:
            ns_map.setdefault(f"__pkg__:{info.package}", mod_key)

    if spec.id == "go":
        gomod = root / "go.mod"
        if gomod.is_file():
            m = re.search(r"^\s*module\s+(\S+)", read_text(gomod), re.MULTILINE)
            if m:
                ns_map["__go_module__"] = m.group(1).strip()

    elif spec.id == "php":
        comp = root / "composer.json"
        if comp.is_file():
            try:
                data = json.loads(read_text(comp))
                for sec in ("autoload", "autoload-dev"):
                    psr4 = data.get(sec, {}).get("psr-4", {})
                    if isinstance(psr4, dict):
                        for prefix, target_dir in psr4.items():
                            if isinstance(target_dir, list):
                                target_dir = target_dir[0] if target_dir else ""
                            clean_prefix = prefix.strip("\\")
                            clean_dir = str(target_dir).strip("/")
                            ns_map[f"__psr4__:{clean_prefix}"] = clean_dir
            except Exception:
                pass

    elif spec.id == "jsts":
        for cfg_name in ("tsconfig.json", "jsconfig.json"):
            cfg_path = root / cfg_name
            if cfg_path.is_file():
                try:
                    data = json.loads(_strip_jsonc_comments(read_text(cfg_path)))
                    co = data.get("compilerOptions", {})
                    base_url = co.get("baseUrl", ".")
                    paths = co.get("paths", {})
                    if isinstance(paths, dict):
                        for alias_pat, targets in paths.items():
                            if not targets or not isinstance(targets, list):
                                continue
                            alias_prefix = alias_pat.rstrip("*")
                            target_prefix = str(targets[0]).rstrip("*")
                            joined = PurePosixPath(base_url) / target_prefix
                            ns_map[f"__ts_alias__:{alias_prefix}"] = joined.as_posix().lstrip("./")
                except Exception:
                    pass

    elif spec.id == "dart":
        pub = root / "pubspec.yaml"
        if pub.is_file():
            m = re.search(r"^\s*name:\s*([A-Za-z0-9_]+)", read_text(pub), re.MULTILINE)
            if m:
                ns_map["__dart_pkg__"] = m.group(1).strip()

    return ns_map


def resolve_import_all(
    importer: str,
    raw_import: str,
    mods: dict[str, ModuleInfo],
    ns_map: dict[str, str],
    spec: LangSpec,
) -> list[str]:
    """Resolve `raw_import` from `importer` into all matching internal module names."""
    raw = raw_import.strip().strip("'\"")
    if not raw:
        return []

    importer_info = mods.get(importer)

    if spec.id == "jsts":
        rewritten_from_alias = False
        for k, v in ns_map.items():
            if k.startswith("__ts_alias__:"):
                alias_prefix = k.split(":", 1)[1]
                if raw.startswith(alias_prefix):
                    rest = raw[len(alias_prefix) :]
                    raw = f"./{v.rstrip('/')}/{rest.lstrip('/')}"
                    rewritten_from_alias = True
                    break
        if raw.startswith("."):
            if importer_info is not None:
                base_dir = PurePosixPath(".") if rewritten_from_alias else PurePosixPath(importer).parent
                norm_parts: list[str] = []
                for part in (base_dir / raw).as_posix().split("/"):
                    if part in ("", "."):
                        continue
                    if part == "..":
                        if norm_parts:
                            norm_parts.pop()
                    else:
                        norm_parts.append(part)
                cand_base = "/".join(norm_parts)
                stripped_ext = re.sub(r"\.(?:js|jsx|mjs|cjs|ts|tsx)$", "", cand_base)
                for probe in (cand_base, stripped_ext, f"{cand_base}/index", f"{stripped_ext}/index"):
                    if probe in mods:
                        return [probe]
                    if probe in ns_map and ns_map[probe] in mods:
                        return [ns_map[probe]]
        return []

    if spec.id == "go":
        go_mod = ns_map.get("__go_module__")
        sub_pkg = None
        if go_mod and (raw == go_mod or raw.startswith(go_mod + "/")):
            sub_pkg = raw[len(go_mod) :].lstrip("/") or "."
        elif raw.startswith("./") or raw.startswith("../"):
            base_dir = PurePosixPath(importer).parent
            sub_pkg = (base_dir / raw).as_posix().lstrip("./")
        if sub_pkg is not None:
            hits = [
                m for m, info in mods.items()
                if (info.package == sub_pkg) or (sub_pkg == "." and info.package in (None, ".", "main"))
            ]
            return sorted(hits)
        return []

    if spec.id == "rust":
        clean = raw.split(" as ")[0].strip()
        if clean.startswith(("crate::", "super::", "self::")):
            if clean.startswith("self::") and importer_info:
                base = importer if importer_info.is_pkg_init else (importer_info.package or "crate")
                clean = f"{base}::{clean[6:]}"
            elif clean.startswith("super::") and importer_info:
                base = importer if importer_info.is_pkg_init else (importer_info.package or "crate")
                parts = base.split("::")
                while clean.startswith("super::"):
                    clean = clean[7:]
                    if len(parts) > 1:
                        parts.pop()
                clean = "::".join(parts) + (f"::{clean}" if clean else "")
            segs = clean.split("::")
            for i in range(len(segs), 0, -1):
                cand = "::".join(segs[:i])
                if cand in mods:
                    return [cand]
            return []
        if "::" not in clean and importer_info:
            base = importer if importer_info.is_pkg_init else (importer_info.package or "crate")
            cand = f"{base}::{clean}"
            if cand in mods:
                return [cand]
        return []

    if spec.id == "cpp":
        clean = raw.replace("\\", "/")
        hits: list[str] = []
        if importer_info:
            rel_cand = (PurePosixPath(importer).parent / clean).as_posix().lstrip("./")
            if rel_cand in ns_map and ns_map[rel_cand] in mods:
                hits.append(ns_map[rel_cand])
        if not hits and clean in ns_map and ns_map[clean] in mods:
            hits.append(ns_map[clean])
        if not hits:
            fname = PurePosixPath(clean).name
            if fname in ns_map and ns_map[fname] in mods:
                hits.append(ns_map[fname])
        expanded = list(hits)
        for h in hits:
            h_info = mods.get(h)
            if h_info and h_info.path.suffix.lower() in (".h", ".hh", ".hpp", ".hxx"):
                stem = h_info.path.stem
                for m, m_info in mods.items():
                    if m != h and m_info.path.stem == stem and m_info.path.suffix.lower() in (".c", ".cc", ".cpp", ".cxx"):
                        if m not in expanded:
                            expanded.append(m)
        return expanded

    if spec.id in ("java", "kotlin", "scala"):
        clean = raw.rstrip(";")
        if clean.endswith(".*") or clean.endswith("._"):
            pkg_prefix = clean[:-2]
            return sorted(m for m, info in mods.items() if info.package == pkg_prefix)
        if clean in mods:
            return [clean]
        if "." in clean:
            parent = clean.rsplit(".", 1)[0]
            if parent in mods:
                return [parent]
        return []

    if spec.id == "csharp":
        clean = raw.rstrip(";")
        hits = [
            m for m, info in mods.items()
            if info.package == clean or (info.package and clean.startswith(info.package + "."))
        ]
        if hits:
            return sorted(hits)
        return []

    if spec.id == "php":
        clean = raw.strip().lstrip("\\")
        if clean.endswith(".php"):
            rel = clean.lstrip("./")
            if importer_info:
                cand = (PurePosixPath(importer).parent / rel).as_posix().lstrip("./")
                if cand in ns_map and ns_map[cand] in mods:
                    return [ns_map[cand]]
            if rel in ns_map and ns_map[rel] in mods:
                return [ns_map[rel]]
            fname = PurePosixPath(rel).name
            if fname in ns_map and ns_map[fname] in mods:
                return [ns_map[fname]]
        for k, target_dir in ns_map.items():
            if k.startswith("__psr4__:"):
                prefix = k.split(":", 1)[1]
                if clean.startswith(prefix):
                    sub = clean[len(prefix) :].lstrip("\\").replace("\\", "/")
                    cand = f"{target_dir}/{sub}.php".lstrip("/")
                    if cand in ns_map and ns_map[cand] in mods:
                        return [ns_map[cand]]
        parts = clean.split("\\")
        cls_name = parts[-1]
        ns_part = "\\".join(parts[:-1])
        hits = [
            m for m, info in mods.items()
            if info.path.stem == cls_name and (not ns_part or info.package == ns_part)
        ]
        return sorted(hits)

    if spec.id == "ruby":
        clean = raw.removesuffix(".rb")
        if importer_info:
            rel_cand = (PurePosixPath(importer).parent / clean).as_posix().lstrip("./")
            for probe in (rel_cand, f"{rel_cand}.rb"):
                if probe in ns_map and ns_map[probe] in mods:
                    return [ns_map[probe]]
        for probe in (clean, f"{clean}.rb", f"lib/{clean}.rb"):
            if probe in ns_map and ns_map[probe] in mods:
                return [ns_map[probe]]
        return []

    if spec.id == "swift":
        hits = [m for m, info in mods.items() if info.package == raw]
        return sorted(hits)

    if spec.id == "dart":
        if raw.startswith("dart:"):
            return []
        if raw.startswith("package:"):
            pkg_and_path = raw[len("package:") :]
            if "/" in pkg_and_path:
                pkg_name, rel_path = pkg_and_path.split("/", 1)
                own_pkg = ns_map.get("__dart_pkg__")
                if own_pkg and pkg_name == own_pkg:
                    if rel_path in ns_map and ns_map[rel_path] in mods:
                        return [ns_map[rel_path]]
            return []
        if importer_info:
            base = PurePosixPath(importer).parent
            norm: list[str] = []
            for p in (base / raw).as_posix().split("/"):
                if p in ("", "."):
                    continue
                if p == "..":
                    if norm:
                        norm.pop()
                else:
                    norm.append(p)
            cand = "/".join(norm)
            if cand in ns_map and ns_map[cand] in mods:
                return [ns_map[cand]]
        if raw in ns_map and ns_map[raw] in mods:
            return [ns_map[raw]]
        return []

    if spec.id == "lua":
        dotted = raw.removesuffix(".lua").replace("/", ".").lstrip(".")
        if dotted in mods:
            return [dotted]
        if dotted in ns_map and ns_map[dotted] in mods:
            return [ns_map[dotted]]
        return []

    if spec.id == "elixir":
        hits = [
            m for m, info in mods.items()
            if info.package == raw or (info.package and info.package.endswith("." + raw))
        ]
        return sorted(hits)

    return []


def resolve_import(
    importer: str,
    raw_import: str,
    mods: dict[str, ModuleInfo],
    ns_map: dict[str, str],
    spec: LangSpec,
) -> str | None:
    """Resolve `raw_import` to the primary matching internal module name, or None."""
    hits = resolve_import_all(importer, raw_import, mods, ns_map, spec)
    return hits[0] if hits else None


def find_symbol_candidates(
    mods: dict[str, ModuleInfo],
    graph: ModuleGraph,
    symbol: str,
    spec: LangSpec | None = None,
) -> list[str]:
    """Return sorted module names that define `symbol`."""
    exact: list[str] = []
    for mod_name, defn_list in graph.defns.items():
        if any(d.name == symbol and d.kind != "import" for d in defn_list):
            exact.append(mod_name)
    if exact:
        return sorted(set(exact))

    reexports = [
        mod_name
        for mod_name, defn_list in graph.defns.items()
        if any(d.name == symbol for d in defn_list)
    ]
    if reexports:
        return sorted(set(reexports))

    stem_hits = [
        mod_name
        for mod_name, info in mods.items()
        if info.path.stem == symbol or mod_name.split(".")[-1] == symbol
    ]
    return sorted(set(stem_hits))
