"""BFS dependency graph traversal, stdlib classification, and manifest version resolution across 15 languages."""

from __future__ import annotations

import ast
import json
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path

from yoink.errors import SafetyError
from yoink.lang import LangSpec
from yoink.lang.resolve import build_namespace_map, resolve_import_all
from yoink.model import Closure, ExternalDep, ImportEdge, ModuleGraph, ModuleInfo, Unresolved
from yoink.slice import needed_defns, parse_module, stmt_defined_names
from yoink.util import read_text

_PYTHON_STDLIB: frozenset[str] = frozenset(getattr(sys, "stdlib_module_names", ())) | {
    "typing",
    "typing_extensions",
    "__future__",
    "builtins",
    "dataclasses",
    "pathlib",
    "collections",
    "itertools",
    "functools",
    "enum",
    "abc",
    "re",
    "os",
    "sys",
    "json",
    "math",
    "time",
    "datetime",
    "logging",
    "subprocess",
    "shutil",
    "tempfile",
    "hashlib",
    "ast",
    "inspect",
    "io",
    "unittest",
    "contextlib",
    "concurrent",
    "asyncio",
    "urllib",
    "http",
    "socket",
    "ssl",
    "sqlite3",
    "csv",
    "copy",
    "pprint",
    "struct",
    "threading",
    "multiprocessing",
    "queue",
    "signal",
    "traceback",
    "warnings",
    "weakref",
    "zipfile",
    "tarfile",
    "gzip",
    "bz2",
    "lzma",
    "zlib",
    "tomllib",
    "xml",
    "html",
    "email",
    "base64",
    "binascii",
    "hmac",
    "secrets",
    "uuid",
    "stat",
    "glob",
    "fnmatch",
    "shlex",
    "argparse",
    "configparser",
    "importlib",
    "pkgutil",
    "platform",
    "ctypes",
    "decimal",
    "fractions",
    "random",
    "statistics",
    "string",
    "textwrap",
    "unicodedata",
    "operator",
    "heapq",
    "bisect",
    "array",
}

_PYPI_IMPORT_ALIASES: dict[str, str] = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "skimage": "scikit-image",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "jwt": "PyJWT",
    "dateutil": "python-dateutil",
    "attr": "attrs",
    "Crypto": "pycryptodome",
    "Cryptodome": "pycryptodomex",
    "git": "GitPython",
    "fitz": "PyMuPDF",
    "serial": "pyserial",
    "usb": "pyusb",
    "OpenSSL": "pyOpenSSL",
    "magic": "python-magic",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "MySQLdb": "mysqlclient",
    "psycopg2": "psycopg2-binary",
    "nacl": "PyNaCl",
    "graphql": "graphql-core",
    "pkg_resources": "setuptools",
}

_REQ_RE = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(?:(==|~=|>=|<=|>|<|!=)\s*([A-Za-z0-9.*!_+-]+))?"
)


def _norm_pkg_key(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def _parse_manifest_deps(root: Path, language: str) -> dict[str, tuple[str, str | None, str]]:
    """Parse repository manifest files into `norm_key -> (canonical_name, version, evidence_file)`."""
    root = Path(root).resolve()
    deps: dict[str, tuple[str, str | None, str]] = {}

    if language == "python":
        pyproj = root / "pyproject.toml"
        if pyproj.is_file():
            try:
                data = tomllib.loads(read_text(pyproj))
                proj = data.get("project", {})
                raw_list = list(proj.get("dependencies", []))
                for opt_list in proj.get("optional-dependencies", {}).values():
                    if isinstance(opt_list, list):
                        raw_list.extend(opt_list)
                for item in raw_list:
                    m = _REQ_RE.match(str(item))
                    if m:
                        pkg = m.group(1)
                        ver = f"{m.group(2)}{m.group(3)}" if m.group(2) and m.group(3) else None
                        deps[_norm_pkg_key(pkg)] = (pkg, ver, "pyproject.toml")
                poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
                if isinstance(poetry_deps, dict):
                    for pkg, spec in poetry_deps.items():
                        if pkg.lower() == "python":
                            continue
                        ver = spec if isinstance(spec, str) else (spec.get("version") if isinstance(spec, dict) else None)
                        deps[_norm_pkg_key(pkg)] = (pkg, str(ver) if ver else None, "pyproject.toml")
            except Exception:
                pass

        for req_file in ("requirements.txt", "requirements-dev.txt"):
            req_path = root / req_file
            if req_path.is_file():
                for line in read_text(req_path).splitlines():
                    s = line.split("#", 1)[0].strip()
                    if not s or s.startswith("-"):
                        continue
                    m = _REQ_RE.match(s)
                    if m:
                        pkg = m.group(1)
                        ver = f"{m.group(2)}{m.group(3)}" if m.group(2) and m.group(3) else None
                        deps.setdefault(_norm_pkg_key(pkg), (pkg, ver, req_file))

    elif language == "jsts":
        pkg_json = root / "package.json"
        if pkg_json.is_file():
            try:
                data = json.loads(read_text(pkg_json))
                for sec in ("dependencies", "devDependencies", "peerDependencies"):
                    sec_dict = data.get(sec, {})
                    if isinstance(sec_dict, dict):
                        for pkg, ver in sec_dict.items():
                            deps[pkg] = (pkg, str(ver), "package.json")
            except Exception:
                pass

    elif language == "go":
        gomod = root / "go.mod"
        if gomod.is_file():
            text = read_text(gomod)
            for m in re.finditer(r"^\s*([A-Za-z0-9_.-]+\.[A-Za-z0-9_./-]+)\s+(v[0-9][^\s/]*)", text, re.MULTILINE):
                pkg, ver = m.group(1), m.group(2)
                deps[pkg] = (pkg, ver, "go.mod")

    elif language == "rust":
        cargo = root / "Cargo.toml"
        if cargo.is_file():
            try:
                data = tomllib.loads(read_text(cargo))
                for sec in ("dependencies", "dev-dependencies", "build-dependencies"):
                    sec_dict = data.get(sec, {})
                    if isinstance(sec_dict, dict):
                        for pkg, val in sec_dict.items():
                            ver = val if isinstance(val, str) else (val.get("version") if isinstance(val, dict) else None)
                            crate_ident = pkg.replace("-", "_")
                            deps[crate_ident] = (pkg, str(ver) if ver else None, "Cargo.toml")
                            deps[pkg] = (pkg, str(ver) if ver else None, "Cargo.toml")
            except Exception:
                pass

    elif language == "php":
        comp = root / "composer.json"
        if comp.is_file():
            try:
                data = json.loads(read_text(comp))
                for sec in ("require", "require-dev"):
                    sec_dict = data.get(sec, {})
                    if isinstance(sec_dict, dict):
                        for pkg, ver in sec_dict.items():
                            if pkg == "php" or pkg.startswith("ext-"):
                                continue
                            deps[pkg.lower()] = (pkg, str(ver), "composer.json")
            except Exception:
                pass

    elif language == "ruby":
        gemfile = root / "Gemfile"
        if gemfile.is_file():
            for m in re.finditer(r"""^\s*gem\s+['"]([^'"]+)['"](?:\s*,\s*['"]([^'"]+)['"])?""", read_text(gemfile), re.MULTILINE):
                pkg, ver = m.group(1), m.group(2)
                deps[_norm_pkg_key(pkg)] = (pkg, ver, "Gemfile")

    elif language == "csharp":
        for csproj in root.glob("*.csproj"):
            try:
                tree = ET.fromstring(read_text(csproj))
                for elem in tree.iter("PackageReference"):
                    inc = elem.attrib.get("Include") or elem.attrib.get("Update")
                    ver = elem.attrib.get("Version")
                    if inc:
                        deps[inc] = (inc, ver, csproj.name)
                        deps[_norm_pkg_key(inc)] = (inc, ver, csproj.name)
                        deps[inc.split(".")[0]] = (inc, ver, csproj.name)
            except Exception:
                pass

    elif language in ("java", "kotlin"):
        pom = root / "pom.xml"
        if pom.is_file():
            text = read_text(pom)
            for m in re.finditer(
                r"<dependency>\s*<groupId>([^<]+)</groupId>\s*<artifactId>([^<]+)</artifactId>(?:\s*<version>([^<]+)</version>)?",
                text,
                re.DOTALL,
            ):
                grp, art, ver = m.group(1).strip(), m.group(2).strip(), (m.group(3) or "").strip() or None
                coord = f"{grp}:{art}"
                deps[grp] = (coord, ver, "pom.xml")
                deps[art] = (coord, ver, "pom.xml")
        for gname in ("build.gradle", "build.gradle.kts"):
            gpath = root / gname
            if gpath.is_file():
                for m in re.finditer(r"""(?:implementation|api|compileOnly|testImplementation)\s*\(?\s*['"]([^:'"]+):([^:'"]+)(?::([^'"]+))?['"]""", read_text(gpath)):
                    grp, art, ver = m.group(1), m.group(2), m.group(3)
                    coord = f"{grp}:{art}"
                    deps[grp] = (coord, ver, gname)
                    deps[art] = (coord, ver, gname)

    elif language == "dart":
        pub = root / "pubspec.yaml"
        if pub.is_file():
            in_deps = False
            for line in read_text(pub).splitlines():
                if re.match(r"^(?:dependencies|dev_dependencies):\s*$", line):
                    in_deps = True
                    continue
                if in_deps and re.match(r"^[A-Za-z0-9_]+:", line):
                    in_deps = False
                if in_deps:
                    m = re.match(r"^\s{2}([A-Za-z0-9_]+):\s*([^#\s]+)?", line)
                    if m and m.group(1) != "flutter":
                        deps[m.group(1)] = (m.group(1), m.group(2), "pubspec.yaml")

    elif language == "swift":
        pkg_swift = root / "Package.swift"
        if pkg_swift.is_file():
            for m in re.finditer(r"""\.package\s*\([^)]*url:\s*["']([^"']+)["'][^)]*(?:from:\s*["']([^"']+)["'])?""", read_text(pkg_swift)):
                url, ver = m.group(1), m.group(2)
                name = url.rstrip("/").split("/")[-1].removesuffix(".git")
                deps[name] = (name, ver, "Package.swift")

    elif language == "scala":
        sbt = root / "build.sbt"
        if sbt.is_file():
            for m in re.finditer(r'"([^"]+)"\s*%%?\s*"([^"]+)"\s*%\s*"([^"]+)"', read_text(sbt)):
                org, art, ver = m.group(1), m.group(2), m.group(3)
                coord = f"{org}:{art}"
                deps[org] = (coord, ver, "build.sbt")
                deps[art] = (coord, ver, "build.sbt")

    elif language == "elixir":
        mix = root / "mix.exs"
        if mix.is_file():
            for m in re.finditer(r"""\{:([A-Za-z0-9_]+)\s*,\s*["']([^"']+)["']""", read_text(mix)):
                pkg, ver = m.group(1), m.group(2)
                deps[pkg] = (pkg, ver, "mix.exs")

    return deps


def _resolve_python_import(
    edge: ImportEdge,
    mods: dict[str, ModuleInfo],
) -> list[str]:
    """Resolve a Python ImportEdge to matching internal module names."""
    importer_info = mods.get(edge.importer)
    candidates: list[str] = []

    if edge.level > 0:
        if importer_info is None:
            return []
        base_pkg = importer_info.name if importer_info.is_pkg_init else (importer_info.package or "")
        parts = [p for p in base_pkg.split(".") if p]
        up = edge.level - 1
        if up > len(parts):
            return []
        prefix_parts = parts[: len(parts) - up]
        if edge.module:
            prefix_parts.extend(edge.module.split("."))
        base_mod = ".".join(prefix_parts)
        if base_mod in mods:
            candidates.append(base_mod)
        for orig_name, _ in edge.names:
            sub_mod = f"{base_mod}.{orig_name}" if base_mod else orig_name
            if sub_mod in mods and sub_mod not in candidates:
                candidates.append(sub_mod)
        return candidates

    raw = edge.module
    if not raw:
        return []
    if raw in mods:
        candidates.append(raw)
    if not candidates:
        segs = raw.split(".")
        for i in range(len(segs) - 1, 0, -1):
            prefix = ".".join(segs[:i])
            if prefix in mods and prefix not in candidates:
                candidates.append(prefix)
                break
    for orig_name, _ in edge.names:
        sub_mod = f"{raw}.{orig_name}"
        if sub_mod in mods and sub_mod not in candidates:
            candidates.append(sub_mod)
    return candidates


def _is_stdlib(raw_mod: str, language: str, spec: LangSpec | None) -> str | None:
    """Return canonical stdlib name if `raw_mod` belongs to the language standard library, else None."""
    if language == "python":
        top = raw_mod.split(".")[0]
        return top if top in _PYTHON_STDLIB else None

    if spec is None:
        return None

    if language == "rust":
        top = raw_mod.split("::")[0]
        if top in spec.std_libs:
            return top

    for pfx in spec.stdlib_prefixes:
        if raw_mod.startswith(pfx):
            return raw_mod
    if raw_mod in spec.std_libs:
        return raw_mod

    if language == "jsts":
        if raw_mod.startswith("node:"):
            return raw_mod
        base = raw_mod.split("/")[0]
        if base in spec.std_libs:
            return raw_mod
    elif language == "go":
        top = raw_mod.split("/")[0]
        if "." not in top and (raw_mod in spec.std_libs or top in spec.std_libs):
            return raw_mod
    elif language == "cpp":
        if raw_mod in spec.std_libs:
            return raw_mod
    elif language in ("java", "kotlin", "scala", "csharp", "swift"):
        top = raw_mod.split(".")[0]
        if top in spec.std_libs:
            return top
    elif language in ("ruby", "lua", "elixir", "php"):
        if raw_mod in spec.std_libs:
            return raw_mod
    return None


def _external_pkg_name(raw_mod: str, language: str) -> str | None:
    """Extract canonical third-party package identifier from an unresolved import string."""
    if not raw_mod or raw_mod.startswith("."):
        return None
    if language == "python":
        top = raw_mod.split(".")[0]
        return _PYPI_IMPORT_ALIASES.get(top, top)
    if language == "jsts":
        if raw_mod.startswith(("/", "http://", "https://")):
            return None
        parts = raw_mod.split("/")
        if raw_mod.startswith("@") and len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
        return parts[0]
    if language == "go":
        parts = raw_mod.split("/")
        if "." in parts[0] and len(parts) >= 3:
            return "/".join(parts[:3])
        return raw_mod
    if language == "rust":
        top = raw_mod.split("::")[0]
        if top in ("crate", "super", "self"):
            return None
        return top
    if language == "dart":
        if raw_mod.startswith("package:"):
            return raw_mod[len("package:") :].split("/")[0]
        return None
    if language == "php":
        if raw_mod.endswith(".php"):
            return None
        parts = raw_mod.strip("\\").split("\\")
        return "\\".join(parts[:2]) if len(parts) >= 2 else parts[0]
    if language in ("java", "kotlin", "scala"):
        parts = raw_mod.rstrip(".*_").split(".")
        return ".".join(parts[:2]) if len(parts) >= 2 else parts[0]
    if language == "csharp":
        return raw_mod
    return raw_mod


def _python_used_internal_import_lines(
    graph: ModuleGraph,
    closure: Closure,
    mod_name: str,
    target_symbol: str | None,
    target_module: str | None,
) -> set[int] | None:
    """Return line numbers of imports in `mod_name` whose bound names are actually referenced by
    the needed definitions in `mod_name`."""
    if target_symbol is None:
        return None
    info = graph.modules.get(mod_name)
    if info is None:
        return None
    try:
        tree = parse_module(info)
        keep_names = needed_defns(
            graph,
            closure,
            mod_name,
            target_symbol=target_symbol,
            target_module=target_module,
        )
        used_names: set[str] = set(keep_names)
        for stmt in tree.body:
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                continue
            if stmt_defined_names(stmt) & keep_names:
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                        used_names.add(sub.id)

        active_lines: set[int] = set()
        for stmt in tree.body:
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                bound = {(a.asname or a.name).split(".")[0] for a in stmt.names if a.name != "*"}
                if not bound or (bound & used_names):
                    active_lines.add(stmt.lineno)
        return active_lines
    except Exception:
        return None


def compute_closure(
    graph: ModuleGraph,
    target_module: str | None = None,
    target_symbol: str | None = None,
    *,
    source_root: Path,
    spec: LangSpec | None = None,
    max_depth: int | None = None,
    allow_gpl: bool = False,
) -> Closure:
    """Traverse `ModuleGraph` via BFS to compute the complete dependency closure."""
    source_root = Path(source_root).resolve()
    if not allow_gpl:
        from yoink.acquire.license import detect_license

        lic = detect_license(source_root)
        if lic and any(g in lic.lower() for g in ("gpl", "agpl", "lgpl")):
            raise SafetyError(
                f"source repository has {lic} license; pass allow_gpl=True or --allow-gpl to proceed"
            )

    language = graph.language
    mods = graph.modules
    resolution = "ast" if language == "python" else "hybrid"
    target_label = (
        f"{target_module}:{target_symbol}"
        if target_module and target_symbol
        else (target_module or target_symbol or "")
    )

    closure = Closure(
        target=target_label,
        language=language,
        resolution=resolution,
    )

    if target_module is None or target_module not in mods:
        return closure

    ns_map = build_namespace_map(source_root, mods, spec) if spec is not None else {}
    manifest_deps = _parse_manifest_deps(source_root, language)

    imports_by_mod: dict[str, list[ImportEdge]] = {}
    for edge in graph.imports:
        imports_by_mod.setdefault(edge.importer, []).append(edge)

    queue: deque[tuple[str, int]] = deque([(target_module, 0)])
    closure.modules.add(target_module)

    if language == "cpp":
        t_info = mods[target_module]
        if t_info.path.suffix.lower() in (".h", ".hh", ".hpp", ".hxx"):
            for m, m_info in mods.items():
                if m != target_module and m_info.path.stem == t_info.path.stem and m_info.path.suffix.lower() in (".c", ".cc", ".cpp", ".cxx"):
                    closure.modules.add(m)
                    queue.append((m, 0))

    ext_seen: dict[str, ExternalDep] = {}

    while queue:
        cur_mod, depth = queue.popleft()
        if max_depth is not None and depth >= max_depth:
            if imports_by_mod.get(cur_mod):
                closure.depth_hit = True
            continue

        active_internal_lines = (
            _python_used_internal_import_lines(graph, closure, cur_mod, target_symbol, target_module)
            if language == "python"
            else None
        )

        edges = imports_by_mod.get(cur_mod, [])
        for edge in edges:
            if edge.kind == "implicit":
                if edge.module in mods and edge.module not in closure.modules:
                    closure.modules.add(edge.module)
                    queue.append((edge.module, depth + 1))
                continue

            if language == "python":
                internal_hits = _resolve_python_import(edge, mods)
            elif spec is not None:
                internal_hits = resolve_import_all(cur_mod, edge.module, mods, ns_map, spec)
            else:
                internal_hits = []

            if internal_hits:
                # Only pull internal modules if the import statement is actually used by the needed symbol slice!
                if active_internal_lines is not None and edge.lineno not in active_internal_lines:
                    continue
                for hit in internal_hits:
                    if hit not in closure.modules:
                        closure.modules.add(hit)
                        queue.append((hit, depth + 1))
                continue

            if (language == "python" and edge.level > 0) or (
                language == "jsts" and edge.module.startswith(".")
            ):
                closure.unresolved.append(
                    Unresolved(
                        file=mods[cur_mod].path.name,
                        lineno=edge.lineno,
                        name=edge.module or "." * edge.level,
                        kind="unresolved_import",
                        detail=f"relative import {edge.module!r} not found in repository",
                    )
                )
                continue

            std_hit = _is_stdlib(edge.module, language, spec)
            if std_hit is not None:
                closure.stdlib.add(std_hit)
                continue

            pkg_name = _external_pkg_name(edge.module, language)
            if pkg_name:
                norm_k = _norm_pkg_key(pkg_name)
                if pkg_name in manifest_deps:
                    canon, ver, ev = manifest_deps[pkg_name]
                elif norm_k in manifest_deps:
                    canon, ver, ev = manifest_deps[norm_k]
                elif pkg_name.split(".")[0] in manifest_deps:
                    canon, ver, ev = manifest_deps[pkg_name.split(".")[0]]
                else:
                    canon, ver, ev = pkg_name, None, f"import in {mods[cur_mod].path.name}"
                if canon not in ext_seen:
                    ext_seen[canon] = ExternalDep(name=canon, version=ver, evidence=ev)

    visited_files = {mods[m].path.name for m in closure.modules if m in mods}
    for u in graph.unresolved:
        if u.file in visited_files:
            closure.unresolved.append(u)

    closure.external = sorted(ext_seen.values(), key=lambda d: d.name.lower())
    return closure
