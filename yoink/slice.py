"""AST and block-based code slicing, intra-module dependency closure, and topological ordering."""

from __future__ import annotations

import ast
from collections import deque

from yoink.errors import ParseError
from yoink.model import Closure, ModuleGraph, ModuleInfo
from yoink.util import read_text


def parse_module(info: ModuleInfo) -> ast.Module:
    """Parse Python module source into AST nodes; raise ParseError on syntax error."""
    text = read_text(info.path)
    try:
        return ast.parse(text, filename=str(info.path))
    except SyntaxError as e:
        raise ParseError(f"syntax error in {info.path}: {e}") from e


def _names_used_in_node(node: ast.AST) -> set[str]:
    return {
        sub.id
        for sub in ast.walk(node)
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load)
    }


def stmt_defined_names(stmt: ast.stmt) -> set[str]:
    """Return all top-level or conditional symbol names bound by `stmt`."""
    names: set[str] = set()
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        names.add(stmt.name)
    elif isinstance(stmt, ast.Assign):
        for tgt in stmt.targets:
            for sub in ast.walk(tgt):
                if isinstance(sub, ast.Name):
                    names.add(sub.id)
    elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        names.add(stmt.target.id)
    elif hasattr(ast, "TypeAlias") and isinstance(stmt, ast.TypeAlias) and isinstance(stmt.name, ast.Name):
        names.add(stmt.name.id)
    elif isinstance(stmt, (ast.Try, ast.If)):
        # Do not treat `if __name__ == "__main__":` or `if TYPE_CHECKING:` as runtime definitions
        if isinstance(stmt, ast.If):
            test_src = ast.unparse(stmt.test).strip()
            if "__name__" in test_src or test_src == "TYPE_CHECKING" or test_src.endswith(".TYPE_CHECKING"):
                return names
        for child in ast.walk(stmt):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(child.name)
            elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                names.add(child.id)
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                for alias in child.names:
                    if alias.name != "*":
                        names.add((alias.asname or alias.name).split(".")[0])
    return names


def needed_defns(
    graph: ModuleGraph,
    closure: Closure,
    module: str,
    bindings: dict[str, dict[str, str]] | None = None,
    target_symbol: str | None = None,
    target_module: str | None = None,
) -> set[str]:
    """Identify required top-level definitions in `module` needed to support `target_symbol`."""
    mod_defns = graph.defns.get(module, [])
    all_defn_names = {d.name for d in mod_defns}
    info = graph.modules.get(module)
    if info is None:
        return set()

    if graph.language != "python":
        if module == target_module and target_symbol:
            text_lines = read_text(info.path).splitlines()
            by_name = {d.name: d for d in mod_defns}
            if target_symbol not in by_name:
                return all_defn_names
            needed = {target_symbol}
            queue = deque([target_symbol])
            while queue:
                cur = queue.popleft()
                d = by_name.get(cur)
                if d is None:
                    continue
                snippet = "\n".join(text_lines[max(0, d.lineno - 1) : d.end_lineno])
                for cand_name in all_defn_names:
                    if cand_name not in needed and cand_name in snippet:
                        needed.add(cand_name)
                        queue.append(cand_name)
            return needed
        return all_defn_names

    tree = parse_module(info)
    node_by_name: dict[str, list[ast.AST]] = {}
    for stmt in tree.body:
        bound = stmt_defined_names(stmt)
        for name in bound:
            all_defn_names.add(name)
            node_by_name.setdefault(name, []).append(stmt)

    seeds: set[str] = set()
    if module == target_module and target_symbol:
        seeds.add(target_symbol)
    else:
        for edge in graph.imports:
            if edge.importer in closure.modules and edge.importer != module:
                for orig_name, _ in edge.names:
                    if orig_name in all_defn_names:
                        seeds.add(orig_name)
        for sym_edge in graph.symbols:
            if sym_edge.module in closure.modules and sym_edge.name in all_defn_names:
                seeds.add(sym_edge.name)

    if not seeds:
        return all_defn_names

    needed: set[str] = set(seeds)
    queue: deque[str] = deque(seeds)
    while queue:
        cur = queue.popleft()
        for ast_node in node_by_name.get(cur, ()):
            for ref in _names_used_in_node(ast_node):
                if ref in all_defn_names and ref not in needed:
                    needed.add(ref)
                    queue.append(ref)

    return needed


def topo_order(
    graph: ModuleGraph,
    modules: set[str],
    root_mod: str | None = None,
) -> list[str]:
    """Compute a deterministic topological sort of `modules` so dependencies precede dependents."""
    if not modules:
        return []

    deps_of: dict[str, set[str]] = {m: set() for m in modules}
    dependents_of: dict[str, set[str]] = {m: set() for m in modules}

    for edge in graph.imports:
        u = edge.importer
        if u not in modules:
            continue
        targets: list[str] = []
        if edge.module in modules:
            targets.append(edge.module)
        elif graph.language == "python":
            from yoink.closure import _resolve_python_import

            targets.extend(m for m in _resolve_python_import(edge, graph.modules) if m in modules)
        for v in targets:
            if v != u and v in modules:
                deps_of[u].add(v)
                dependents_of[v].add(u)

    if graph.language == "cpp":
        for m in modules:
            info = graph.modules.get(m)
            if info and info.path.suffix.lower() in (".c", ".cc", ".cpp", ".cxx"):
                for h in modules:
                    h_info = graph.modules.get(h)
                    if h != m and h_info and h_info.path.stem == info.path.stem and h_info.path.suffix.lower() in (".h", ".hh", ".hpp", ".hxx"):
                        deps_of[m].add(h)
                        dependents_of[h].add(m)

    in_degree = {m: len(deps_of[m]) for m in modules}
    ready = sorted(m for m, deg in in_degree.items() if deg == 0)
    ordered: list[str] = []
    visited: set[str] = set()

    while ready:
        cur = ready.pop(0)
        if cur in visited:
            continue
        visited.add(cur)
        ordered.append(cur)
        for dep in sorted(dependents_of[cur]):
            in_degree[dep] -= 1
            if in_degree[dep] == 0 and dep not in visited:
                ready.append(dep)
                ready.sort()

    for m in sorted(modules):
        if m not in visited and m != root_mod:
            ordered.append(m)
    if root_mod and root_mod in modules:
        if root_mod in ordered:
            ordered.remove(root_mod)
        ordered.append(root_mod)

    return ordered
