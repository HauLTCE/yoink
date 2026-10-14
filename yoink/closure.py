"""Dependency closure: BFS over the import graph + honest classification."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from collections import defaultdict, deque
from pathlib import Path
from typing import TYPE_CHECKING

from yoink.model import (
    Closure,
    ExternalDep,
    ImportEdge,
    ModuleGraph,
    ModuleInfo,
    Unresolved,
)
from yoink.util import posix_rel, read_text

if TYPE_CHECKING:
    from yoink.lang import LangSpec

_REQ_RE = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*"
    r"(?:==|~=|>=|<=|>|<)\s*([A-Za-z0-9][A-Za-z0-9.*+!_-]*)"
)

_GEM_RE = re.compile(r"""^\s*gem\s+['"]([A-Za-z0-9_-]+)['"]\s*(?:,\s*['"]([^'"]+)['"])?""")
_CSPROJ_RE = re.compile(
    r"PackageReference\s+Include\s*=\s*\"([^\"]+)\"[^>]*Version\s*=\s*\"([^\"]+)\""
)
_POM_ART_RE = re.compile(r"<artifactId>\s*([^<\s]+)\s*</artifactId>")
_POM_VER_RE = re.compile(r"<version>\s*([^<\s]+)\s*</version>")


def compute_closure(
    graph: ModuleGraph,
    module_map: dict[str, ModuleInfo],
    target_module: str | None,
    target_symbol: str | None,
    *,
    max_depth: int,
    source_root: Path,
    spec: "LangSpec | None" = None,
    target: str | None = None,
) -> Closure:
    """BFS from the target module; classify edges; never lie about unresolved."""
    source_root = Path(source_root)
    if graph.language == "python":
        closure = _python_closure(
            graph, module_map, target_module, max_depth, source_root
        )
        closure.resolution = "ast"
    else:
        closure = _generic_closure(
            graph, module_map, target_module, max_depth, source_root, spec
        )
        closure.resolution = "text"
    closure.target = target if target is not None else (
        target_module or target_symbol or ""
    )
    return closure


# ---------------------------------------------------------------------------
# python


def _python_closure(
    graph: ModuleGraph,
    mods: dict[str, ModuleInfo],
    target_module: str | None,
    max_depth: int,
    source_root: Path,
) -> Closure:
    pulled: set[str] = set()
    stdlib: set[str] = set()
    external: dict[str, ExternalDep] = {}
    unresolved: list[Unresolved] = list(graph.unresolved)

    by_importer: dict[str, list[ImportEdge]] = defaultdict(list)
    for e in graph.imports:
        by_importer[e.importer].append(e)

    bindings = build_bindings(graph, mods)

    if target_module is None:
        return Closure(target="", language="python", resolution="ast")

    seeds = [target_module]
    seen: set[str] = set()
    queue: deque[tuple[str, int]] = deque((s, 0) for s in seeds)
    depth_hit = False
    while queue:
        mod, depth = queue.popleft()
        if mod in seen:
            continue
        seen.add(mod)
        pulled.add(mod)
        if depth >= max_depth:
            depth_hit = True
            continue
        for e in by_importer.get(mod, []):
            if e.kind == "type_checking":
                continue
            _classify_edge(
                e, mod, mods, graph, bindings, pulled, stdlib, external,
                unresolved, queue, depth, source_root,
            )

    _pull_symbol_modules(
        pulled, graph, mods, bindings, stdlib, external, unresolved,
        max_depth, source_root,
    )

    unresolved.extend(_symbol_unresolved(pulled, graph, mods, source_root))

    return Closure(
        target=target_module,
        language="python",
        resolution="ast",
        modules=pulled,
        external=sorted(external.values(), key=lambda d: d.name),
        stdlib=stdlib,
        unresolved=_dedupe_unresolved(unresolved),
        depth_hit=depth_hit,
    )


def _classify_edge(
    e: ImportEdge,
    importer: str,
    mods: dict[str, ModuleInfo],
    graph: ModuleGraph,
    bindings: dict[str, dict[str, str]],
    pulled: set[str],
    stdlib: set[str],
    external: dict[str, ExternalDep],
    unresolved: list[Unresolved],
    queue: deque[tuple[str, int]],
    depth: int,
    source_root: Path,
) -> None:
    mod = e.module
    if not mod:
        return
    resolved = _resolve_in_repo(mod, mods)
    if resolved is not None:
        if resolved not in pulled:
            queue.append((resolved, depth + 1))
        # from X import name where name lives deeper: pull defining module
        for name, _asname in e.names:
            origin = _follow_binding(resolved, name, bindings, mods)
            if origin and origin != resolved and origin not in pulled:
                queue.append((origin, depth + 1))
        return
    root_seg = mod.split(".")[0]
    if root_seg in sys.stdlib_module_names:
        stdlib.add(root_seg)
        return
    if _exists_on_disk(root_seg, source_root):
        unresolved.append(
            Unresolved(
                _edge_file(importer, mods, source_root),
                e.lineno,
                root_seg,
                "unresolvable_name",
                "excluded by .gitignore",
            )
        )
        return
    dep = _external_dep(root_seg, source_root, importer, mods)
    external.setdefault(dep.name, dep)


def _resolve_in_repo(mod: str, mods: dict[str, ModuleInfo]) -> str | None:
    if mod in mods:
        return mod
    # progressive: a.b.c may resolve to a.b package with c a name inside
    parts = mod.split(".")
    for k in range(len(parts) - 1, 0, -1):
        cand = ".".join(parts[:k])
        if cand in mods:
            return cand
    return None


def _follow_binding(
    mod: str,
    name: str,
    bindings: dict[str, dict[str, str]],
    mods: dict[str, ModuleInfo],
    seen: set[str] | None = None,
) -> str | None:
    """Chase `from a import name` through re-export chains to the definer."""
    seen = seen or set()
    cur = mod
    for _ in range(64):
        if cur in seen:
            return None
        seen.add(cur)
        origin = bindings.get(cur, {}).get(name)
        if origin is None:
            return cur  # defined here (or nowhere we can see); stop the chase
        nxt = _resolve_in_repo(origin, mods)
        if nxt is None or nxt == cur:
            return nxt
        cur = nxt
    return cur


def _pull_symbol_modules(
    pulled: set[str],
    graph: ModuleGraph,
    mods: dict[str, ModuleInfo],
    bindings: dict[str, dict[str, str]],
    stdlib: set[str],
    external: dict[str, ExternalDep],
    unresolved: list[Unresolved],
    max_depth: int,
    source_root: Path,
) -> None:
    # names used-but-unbound in pulled modules might be importable names —
    # try resolving them against the module map one more hop
    changed = True
    rounds = 0
    while changed and rounds < 4:
        changed = False
        rounds += 1
        for sym in graph.symbols:
            if sym.module not in pulled:
                continue
            for e in graph.imports:
                if e.importer != sym.module:
                    continue
                resolved = _resolve_in_repo(e.module, mods)
                if resolved is None or resolved in pulled:
                    continue
                names = {n for n, _ in e.names}
                if sym.name in names or sym.name == e.module.split(".")[-1]:
                    pulled.add(resolved)
                    changed = True


def _symbol_unresolved(
    pulled: set[str],
    graph: ModuleGraph,
    mods: dict[str, ModuleInfo],
    source_root: Path,
) -> list[Unresolved]:
    out: list[Unresolved] = []
    seen: set[tuple[str, str]] = set()
    by_importer: dict[str, set[str]] = defaultdict(set)
    for e in graph.imports:
        for n, a in e.names:
            by_importer[e.importer].add(a or n)
    for sym in graph.symbols:
        if sym.module not in pulled:
            continue
        if sym.name in by_importer.get(sym.module, ()):
            continue  # bound by an edge; not truly unresolvable
        info = mods.get(sym.module)
        f = _info_file(info, source_root)
        key = (f, sym.name)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            Unresolved(f, sym.lineno, sym.name, "unresolvable_name", "used but never bound")
        )
    return out


def _edge_file(importer: str, mods: dict[str, ModuleInfo], root: Path) -> str:
    info = mods.get(importer)
    return _info_file(info, root)


def _info_file(info: ModuleInfo | None, root: Path) -> str:
    if info is None:
        return ""
    try:
        return posix_rel(info.path, root)
    except ValueError:
        return info.path.name


def _exists_on_disk(root_seg: str, source_root: Path) -> bool:
    """Dotted-name -> file resolution against the raw fs (no ignore filter)."""
    if not root_seg:
        return False
    for cand in (
        source_root / f"{root_seg}.py",
        source_root / root_seg / "__init__.py",
        source_root / "src" / f"{root_seg}.py",
        source_root / "src" / root_seg / "__init__.py",
    ):
        if cand.exists():
            return True
    return False


def _external_dep(
    root_seg: str, source_root: Path, importer: str, mods: dict[str, ModuleInfo]
) -> ExternalDep:
    version, evidence = lookup_version(root_seg, source_root)
    if not evidence:
        evidence = _edge_file(importer, mods, source_root) or "import"
    return ExternalDep(name=root_seg, version=version, evidence=evidence)


def build_bindings(
    graph: ModuleGraph, mods: dict[str, ModuleInfo]
) -> dict[str, dict[str, str]]:
    """Per-module name -> origin-module map for `from x import n` re-exports."""
    out: dict[str, dict[str, str]] = defaultdict(dict)
    for e in graph.imports:
        if e.importer not in mods:
            continue
        resolved = _resolve_in_repo(e.module, mods)
        if resolved is None:
            continue
        for n, a in e.names:
            bound = a or n
            out[e.importer][bound] = resolved
    return dict(out)


def _dedupe_unresolved(items: list[Unresolved]) -> list[Unresolved]:
    seen: set[tuple[str, str, str]] = set()
    out: list[Unresolved] = []
    for u in items:
        key = (u.file, u.name, u.kind)
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
    return out


# ---------------------------------------------------------------------------
# version lookup


def lookup_version(name: str, source_root: Path) -> tuple[str | None, str]:
    """Find a pinned version for `name` in common dep manifests."""
    source_root = Path(source_root)
    for req in sorted(source_root.glob("requirements*.txt")):
        v = _req_lookup(req, name)
        if v:
            return v, posix_rel(req, source_root)
    pyproject = source_root / "pyproject.toml"
    if pyproject.is_file():
        v = _pyproject_lookup(pyproject, name)
        if v:
            return v, "pyproject.toml"
    pipfile = source_root / "Pipfile"
    if pipfile.is_file():
        v = _pipfile_lookup(pipfile, name)
        if v:
            return v, "Pipfile"
    setupcfg = source_root / "setup.cfg"
    if setupcfg.is_file():
        v = _setupcfg_lookup(setupcfg, name)
        if v:
            return v, "setup.cfg"
    return None, ""


def _norm(name: str) -> str:
    return name.lower().replace("_", "-")


def _req_lookup(path: Path, name: str) -> str | None:
    try:
        for line in read_text(path).splitlines():
            m = _REQ_RE.match(line)
            if m and _norm(m.group(1)) == _norm(name):
                return m.group(2)
    except OSError:
        pass
    return None


def _pyproject_lookup(path: Path, name: str) -> str | None:
    try:
        data = tomllib.loads(read_text(path))
    except (tomllib.TOMLDecodeError, OSError):
        return None
    deps: list[str] = list(data.get("project", {}).get("dependencies", []) or [])
    opt = data.get("project", {}).get("optional-dependencies", {}) or {}
    for group in opt.values():
        deps.extend(group)
    for dep in deps:
        m = _REQ_RE.match(dep)
        if m and _norm(m.group(1)) == _norm(name):
            return m.group(2)
    return None


def _pipfile_lookup(path: Path, name: str) -> str | None:
    try:
        data = tomllib.loads(read_text(path))
    except (tomllib.TOMLDecodeError, OSError):
        return None
    for pkg, ver in (data.get("packages", {}) or {}).items():
        if _norm(pkg) == _norm(name) and isinstance(ver, str):
            return ver.lstrip("=").lstrip() or None
    return None


def _setupcfg_lookup(path: Path, name: str) -> str | None:
    try:
        text = read_text(path)
    except OSError:
        return None
    in_reqs = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if in_reqs:
            if not line.startswith((" ", "\t")):
                in_reqs = False
            else:
                m = _REQ_RE.match(stripped)
                if m and _norm(m.group(1)) == _norm(name):
                    return m.group(2)
                continue
        if stripped.startswith("[") :
            continue
        if stripped.startswith("install_requires"):
            in_reqs = True
            tail = stripped.split("=", 1)[-1].strip()
            if tail:
                m = _REQ_RE.match(tail)
                if m and _norm(m.group(1)) == _norm(name):
                    return m.group(2)
    return None


# ---------------------------------------------------------------------------
# generic (non-python)


def _generic_closure(
    graph: ModuleGraph,
    mods: dict[str, ModuleInfo],
    target_module: str | None,
    max_depth: int,
    source_root: Path,
    spec: "LangSpec | None",
) -> Closure:
    pulled: set[str] = set()
    stdlib: set[str] = set()
    external: dict[str, ExternalDep] = {}
    unresolved: list[Unresolved] = list(graph.unresolved)

    resolve = None
    ns_map: dict[str, str] = {}
    if spec is not None:
        try:
            from yoink.lang.resolve import build_namespace_map, resolve_import

            resolve = resolve_import
            ns_map = build_namespace_map(mods, spec)
        except Exception:
            resolve = None

    by_importer: dict[str, list[ImportEdge]] = defaultdict(list)
    for e in graph.imports:
        by_importer[e.importer].append(e)

    seeds = [target_module] if target_module else []
    seen: set[str] = set()
    queue: deque[tuple[str, int]] = deque((s, 0) for s in seeds if s)
    depth_hit = False
    while queue:
        mod, depth = queue.popleft()
        if mod in seen:
            continue
        seen.add(mod)
        pulled.add(mod)
        if depth >= max_depth:
            depth_hit = True
            continue
        for e in by_importer.get(mod, []):
            if e.kind == "type_checking":
                continue
            raw = e.module
            target_resolved: str | None = None
            if raw in mods:
                target_resolved = raw
            elif resolve is not None and spec is not None:
                try:
                    target_resolved = resolve(mods, spec, mod, raw, ns_map)
                except Exception:
                    target_resolved = None
            if target_resolved:
                if target_resolved not in pulled:
                    queue.append((target_resolved, depth + 1))
                continue
            if _is_stdlib(raw, spec):
                stdlib.add(raw.split(".")[0])
                continue
            dep = _generic_external(raw, source_root, spec)
            external.setdefault(dep.name, dep)

    return Closure(
        target=target_module or "",
        language=graph.language,
        resolution="text",
        modules=pulled,
        external=sorted(external.values(), key=lambda d: d.name),
        stdlib=stdlib,
        unresolved=_dedupe_unresolved(unresolved),
        depth_hit=depth_hit,
    )


def _is_stdlib(raw: str, spec: "LangSpec | None") -> bool:
    if spec is None:
        return False
    for pre in spec.stdlib_prefixes:
        if raw.startswith(pre):
            return True
    if raw in spec.stdlib_names:
        return True
    if raw.split(".")[0] in spec.stdlib_names:
        return True
    if raw.split("::")[0] in spec.stdlib_names:
        return True
    if raw.split("/")[0] in spec.stdlib_names:
        return True
    return False


def _generic_external(raw: str, source_root: Path, spec: "LangSpec | None") -> ExternalDep:
    """Name a generic external dep + fish a version from repo manifests."""
    name = _generic_name(raw, spec)
    version, evidence = _generic_version(name, source_root)
    return ExternalDep(name=name, version=version, evidence=evidence or "import")


def _generic_name(raw: str, spec: "LangSpec | None") -> str:
    lang = spec.id if spec is not None else ""
    s = raw.strip().strip("'\";")
    if lang == "go":
        return s
    if lang == "rust":
        return s.split("::")[0]
    if lang == "jsts" and s.startswith("@"):
        parts = s.split("/")
        return "/".join(parts[:2]) if len(parts) >= 2 else s
    if lang in ("csharp", "java"):
        # package names are dotted namespaces — keep the whole thing
        return s.split("=")[-1].strip()
    if lang == "php":
        return s.split("\\")[0] if "\\" in s else s
    for sep in ("/", "\\", ".", "::"):
        if sep in s:
            return s.split(sep)[0]
    return s


def _generic_version(name: str, source_root: Path) -> tuple[str | None, str]:
    source_root = Path(source_root)
    pkg = source_root / "package.json"
    if pkg.is_file():
        v = _pkg_json_lookup(pkg, name)
        if v:
            return v, "package.json"
    cargo = source_root / "Cargo.toml"
    if cargo.is_file():
        v = _cargo_lookup(cargo, name)
        if v:
            return v, "Cargo.toml"
    for csproj in sorted(source_root.rglob("*.csproj")):
        v = _csproj_lookup(csproj, name)
        if v:
            return v, posix_rel(csproj, source_root)
    pom = source_root / "pom.xml"
    if pom.is_file():
        v = _pom_lookup(pom, name)
        if v:
            return v, "pom.xml"
    gemfile = source_root / "Gemfile"
    if gemfile.is_file():
        v = _gemfile_lookup(gemfile, name)
        if v:
            return v, "Gemfile"
    composer = source_root / "composer.json"
    if composer.is_file():
        v = _composer_lookup(composer, name)
        if v:
            return v, "composer.json"
    return None, ""


def _pkg_json_lookup(path: Path, name: str) -> str | None:
    try:
        data = json.loads(read_text(path))
    except (json.JSONDecodeError, OSError):
        return None
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        deps = data.get(key) or {}
        if name in deps:
            return str(deps[name]).lstrip("^~>=< ")
    return None


def _cargo_lookup(path: Path, name: str) -> str | None:
    try:
        data = tomllib.loads(read_text(path))
    except (tomllib.TOMLDecodeError, OSError):
        return None
    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        deps = data.get(section) or {}
        if name in deps:
            v = deps[name]
            if isinstance(v, str):
                return v
            if isinstance(v, dict) and "version" in v:
                return str(v["version"])
    return None


def _csproj_lookup(path: Path, name: str) -> str | None:
    try:
        text = read_text(path)
    except OSError:
        return None
    for m in _CSPROJ_RE.finditer(text):
        if m.group(1) == name:
            return m.group(2)
    # newer style: <PackageReference Include="x" Version="y" /> order may flip
    for m in re.finditer(
        r"PackageReference[^>]*Include\s*=\s*\"([^\"]+)\"[^>]*?/>", text
    ):
        if m.group(1) == name:
            ver = re.search(r"Version\s*=\s*\"([^\"]+)\"", m.group(0))
            if ver:
                return ver.group(1)
    return None


def _pom_lookup(path: Path, name: str) -> str | None:
    try:
        text = read_text(path)
    except OSError:
        return None
    blocks = re.findall(
        r"<dependency>(.*?)</dependency>", text, flags=re.DOTALL
    )
    for b in blocks:
        art = _POM_ART_RE.search(b)
        ver = _POM_VER_RE.search(b)
        if art and art.group(1) == name and ver:
            return ver.group(1)
    return None


def _gemfile_lookup(path: Path, name: str) -> str | None:
    try:
        for line in read_text(path).splitlines():
            m = _GEM_RE.match(line)
            if m and m.group(1) == name:
                return m.group(2)
    except OSError:
        pass
    return None


def _composer_lookup(path: Path, name: str) -> str | None:
    try:
        data = json.loads(read_text(path))
    except (json.JSONDecodeError, OSError):
        return None
    for key in ("require", "require-dev"):
        deps = data.get(key) or {}
        if name in deps:
            return str(deps[name]).lstrip("^~>=< ")
    return None
