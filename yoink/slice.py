"""Symbol-level slicing helpers: needed names, side effects, topo order."""

from __future__ import annotations

import ast
import heapq
from pathlib import Path

from yoink.errors import ParseError
from yoink.model import Closure, Defn, ModuleGraph, ModuleInfo

_SIDE_OK = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def needed_defns(
    graph: ModuleGraph,
    closure: Closure,
    module: str,
    bindings: dict[str, dict[str, str]],
    target_symbol: str | None = None,
    target_module: str | None = None,
) -> set[str]:
    """Defn names in `module` that the pulled set actually uses.

    A name is needed when the module is the target and the name is the target
    symbol, or when any pulled module imports/binds it from this module, or
    references it as an unbound name that resolves here.
    """
    out: set[str] = set()
    names_of = {d.name for d in graph.defns.get(module, ())}
    if module == target_module:
        if target_symbol:
            out.add(target_symbol)
        else:
            out.update(names_of)
    for e in graph.imports:
        if e.importer not in closure.modules:
            continue
        # `import x` / `import x as y` binds the module object itself — the
        # recorded name equals e.module's last segment, so `x.<member>` reaches
        # every defn. from-imports name real members and fall through below.
        edge_target = e.module
        for n, _a in e.names:
            if n in names_of and (
                e.module == module or bindings.get(e.importer, {}).get(n) == module
            ):
                out.add(n)
            elif (n == edge_target or n == edge_target.split(".")[-1]) and (
                edge_target == module
                or edge_target.endswith("." + module)
                or module.endswith("." + edge_target)
            ):
                out.update(names_of)
    for sym in graph.symbols:
        if sym.module in closure.modules and sym.module != module and sym.name in names_of:
            out.add(sym.name)
    return out


def parse_module(info: ModuleInfo) -> ast.Module:
    """ast.parse one module file; ParseError with file+line on failure."""
    try:
        return ast.parse(info.path.read_bytes(), filename=str(info.path))
    except SyntaxError as e:
        raise ParseError(f"{info.path}:{e.lineno}: {e.msg}") from e


def _is_docstring(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _is_main_guard(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.If):
        return False
    t = stmt.test
    # __name__ == "__main__" in either order
    if isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], ast.Eq):
        sides = [t.left, *t.comparators]
        names = [s for s in sides if isinstance(s, ast.Name) and s.id == "__name__"]
        lits = [
            s for s in sides
            if isinstance(s, ast.Constant) and s.value == "__main__"
        ]
        if names and lits:
            return True
    return False


def _is_type_checking(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.If):
        return False
    t = stmt.test
    if isinstance(t, ast.Name) and t.id == "TYPE_CHECKING":
        return True
    if isinstance(t, ast.Attribute) and t.attr == "TYPE_CHECKING":
        return True
    if isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Invert):
        inner = t.operand
        return (isinstance(inner, ast.Name) and inner.id == "TYPE_CHECKING") or (
            isinstance(inner, ast.Attribute) and inner.attr == "TYPE_CHECKING"
        )
    return False


def _is_all_assign(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.Assign):
        return False
    return any(isinstance(t, ast.Name) and t.id == "__all__" for t in stmt.targets)


def _try_body_safe(stmt: ast.stmt) -> bool:
    """try/except ImportError blocks are import-fallbacks — treat as side-free."""
    if not isinstance(stmt, ast.Try):
        return False
    catch = False
    for h in stmt.handlers:
        t = h.type
        if t is None:
            catch = True
            continue
        names: set[str] = set()
        todo: list[ast.expr] = [t]
        while todo:
            e = todo.pop()
            if isinstance(e, ast.Tuple):
                todo.extend(e.elts)
            elif isinstance(e, ast.Name):
                names.add(e.id)
            elif isinstance(e, ast.Attribute):
                names.add(e.attr)
        if names & {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}:
            catch = True
    if not catch:
        return False
    bodies = list(stmt.body)
    for h in stmt.handlers:
        bodies.extend(h.body)
    bodies.extend(stmt.orelse)
    return all(
        isinstance(s, _SIDE_OK) or _is_docstring(s) or isinstance(s, (ast.Assign, ast.AnnAssign))
        for s in bodies
    )


def module_has_side_effects(tree: ast.Module) -> bool:
    """True when a top-level stmt isn't def/class/import/assign/docstring/guard."""
    for stmt in tree.body:
        if isinstance(stmt, _SIDE_OK):
            continue
        if _is_docstring(stmt) or _is_main_guard(stmt) or _is_type_checking(stmt):
            continue
        if _is_all_assign(stmt):
            continue
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            continue
        if _try_body_safe(stmt):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue
        return True
    return False


def topo_order(
    graph: ModuleGraph, modules: set[str], root_mod: str | None = None
) -> list[str]:
    """Stable Kahn topo of pulled modules over their in-pull edges."""
    edges: dict[str, set[str]] = {m: set() for m in modules}
    indeg: dict[str, int] = {m: 0 for m in modules}
    for e in graph.imports:
        if e.importer not in modules:
            continue
        if e.kind == "type_checking":
            continue
        dep = _resolved_in(e.module, modules)
        if dep is None or dep == e.importer:
            continue
        if dep not in edges[e.importer]:
            edges[e.importer].add(dep)
            indeg[dep] = indeg.get(dep, 0) + 1
    # Kahn over "who do I depend on" — emit deps before dependents means we
    # want order where a module's deps come first. edges[x] = deps of x.
    # invert: a dep must precede its importers — indeg here counts inbound
    # "is dep of" so we flip to compute "how many of my deps remain".
    dep_count: dict[str, int] = {m: len(edges[m]) for m in modules}
    dependents: dict[str, set[str]] = {m: set() for m in modules}
    for m, deps in edges.items():
        for d in deps:
            dependents[d].add(m)
    heap: list[str] = [m for m in modules if dep_count[m] == 0]
    if root_mod in modules:
        # deterministic but seed-first-ish: alphabetical heap already does it
        pass
    heapq.heapify(heap)
    out: list[str] = []
    while heap:
        m = heapq.heappop(heap)
        out.append(m)
        for dep_of_m in dependents[m]:
            dep_count[dep_of_m] -= 1
            if dep_count[dep_of_m] == 0:
                heapq.heappush(heap, dep_of_m)
    if len(out) < len(modules):
        # cycle — append stragglers alphabetically so nothing is lost
        out.extend(sorted(modules - set(out)))
    return out


def _resolved_in(raw: str, modules: set[str]) -> str | None:
    if raw in modules:
        return raw
    parts = raw.split(".")
    for k in range(len(parts) - 1, 0, -1):
        cand = ".".join(parts[:k])
        if cand in modules:
            return cand
    return None
