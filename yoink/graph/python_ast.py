"""Python stdlib-ast graph builder: defns, imports, unbound names, unresolved."""

from __future__ import annotations

import ast
import builtins
from pathlib import Path

from yoink.errors import ParseError
from yoink.model import (
    Defn,
    ImportEdge,
    ModuleGraph,
    ModuleInfo,
    SymbolEdge,
    Unresolved,
)

_BUILTINS = frozenset(dir(builtins)) | {
    "__name__",
    "__file__",
    "__doc__",
    "__package__",
    "__path__",
    "__spec__",
    "__all__",
}

_EXC_NAMES = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}


def build_python_graph(root: Path, mods: dict[str, ModuleInfo]) -> ModuleGraph:
    """Walk every mapped .py file with stdlib ast; no code is ever executed."""
    root = Path(root)
    graph = ModuleGraph(language="python", modules=mods)
    trees: dict[str, ast.Module] = {}
    all_names: dict[str, set[str]] = {}
    for name in sorted(mods):
        info = mods[name]
        try:
            tree = ast.parse(info.path.read_bytes(), filename=str(info.path))
        except SyntaxError as e:
            raise ParseError(f"{info.path}:{e.lineno}: {e.msg}") from e
        except OSError as e:
            raise ParseError(f"{info.path}: {e}") from e
        trees[name] = tree
        defns = _collect_defns(tree)
        graph.defns[name] = defns
        all_names[name] = _public_names(tree, defns)
    for name in sorted(mods):
        _analyze_module(name, trees[name], mods, graph, all_names, root)
    return graph


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _decorators(node: ast.AST) -> tuple[str, ...]:
    out: list[str] = []
    for dec in getattr(node, "decorator_list", []):
        try:
            out.append(ast.unparse(dec))
        except Exception:
            out.append("?")
    return tuple(out)


def _assign_target_name(t: ast.expr) -> str | None:
    if isinstance(t, ast.Name):
        return t.id
    if isinstance(t, ast.Starred) and isinstance(t.value, ast.Name):
        return t.value.id
    return None


def _public_names(tree: ast.Module, defns: list[Defn]) -> set[str]:
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign):
            continue
        for t in stmt.targets:
            if isinstance(t, ast.Name) and t.id == "__all__":
                if isinstance(stmt.value, (ast.List, ast.Tuple, ast.Set)):
                    names: set[str] = set()
                    for el in stmt.value.elts:
                        if isinstance(el, ast.Constant) and isinstance(el.value, str):
                            names.add(el.value)
                    return names
    return {
        d.name.split(".")[0] for d in defns if not d.name.split(".")[0].startswith("_")
    }


def _collect_defns(tree: ast.Module) -> list[Defn]:
    defns: list[Defn] = []
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defns.append(
                Defn(
                    stmt.name,
                    "func",
                    stmt.lineno,
                    stmt.end_lineno or stmt.lineno,
                    _decorators(stmt),
                )
            )
        elif isinstance(stmt, ast.ClassDef):
            defns.append(
                Defn(
                    stmt.name,
                    "class",
                    stmt.lineno,
                    stmt.end_lineno or stmt.lineno,
                    _decorators(stmt),
                )
            )
        elif isinstance(stmt, ast.Assign):
            for t in stmt.targets:
                n = _assign_target_name(t)
                if n:
                    defns.append(
                        Defn(n, "assign", stmt.lineno, stmt.end_lineno or stmt.lineno)
                    )
        elif isinstance(stmt, ast.AnnAssign):
            n = _assign_target_name(stmt.target)
            if n:
                defns.append(
                    Defn(n, "assign", stmt.lineno, stmt.end_lineno or stmt.lineno)
                )
        elif isinstance(stmt, ast.Import):
            for a in stmt.names:
                bound = a.asname or a.name.split(".")[0]
                defns.append(Defn(bound, "import", stmt.lineno, stmt.lineno))
        elif isinstance(stmt, ast.ImportFrom):
            for a in stmt.names:
                if a.name == "*":
                    continue
                bound = a.asname or a.name
                defns.append(Defn(bound, "import", stmt.lineno, stmt.lineno))
    return defns


def resolve_from(
    importer_pkg: str | None, importer_is_init: bool, level: int, module: str | None
) -> str:
    """Resolve `from ... import` to a dotted path; level=1 is the containing pkg.

    importer_pkg is the module's own package. For __init__ files the caller
    passes the module's own dotted name — the init IS the package.
    """
    if level == 0:
        return module or ""
    parts = importer_pkg.split(".") if importer_pkg else []
    base = list(parts[: len(parts) - (level - 1)]) if level > 1 else list(parts)
    if module:
        base.extend(module.split("."))
    return ".".join(base)


def _catches_import_error(node: ast.Try) -> bool:
    for h in node.handlers:
        t = h.type
        if t is None:
            return True
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
        if names & _EXC_NAMES:
            return True
    return False


def _type_check_test(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Invert):
        return _type_check_test(test.operand)
    if isinstance(test, ast.BoolOp):
        return any(_type_check_test(v) for v in test.values)
    return False


def _lit_str(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


class _Ctx:
    """Flags that ride the walk down."""

    __slots__ = ("type_checking", "in_try")

    def __init__(self, type_checking: bool = False, in_try: bool = False):
        self.type_checking = type_checking
        self.in_try = in_try

    def child(self) -> "_Ctx":
        return _Ctx(self.type_checking, self.in_try)


class _Scope:
    """One lexical scope's bound names."""

    __slots__ = ("bound", "globals", "nonlocals", "kind")

    def __init__(self, kind: str) -> None:
        self.bound: set[str] = set()
        self.globals: set[str] = set()
        self.nonlocals: set[str] = set()
        self.kind = kind  # module | func | class | comp


class _Walker:
    def __init__(
        self,
        modname: str,
        info: ModuleInfo,
        mods: dict[str, ModuleInfo],
        graph: ModuleGraph,
        all_names: dict[str, set[str]],
        root: Path,
    ) -> None:
        self.modname = modname
        self.info = info
        self.mods = mods
        self.graph = graph
        self.all_names = all_names
        self.root = root
        self.relfile = _rel(info.path, root)
        self.scopes: list[_Scope] = [_Scope("module")]

    def bind(self, name: str | None) -> None:
        if name:
            self.scopes[-1].bound.add(name)

    def bind_walrus(self, t: ast.expr) -> None:
        # walrus leaks past comprehensions into the enclosing func/module scope
        if isinstance(t, ast.Name):
            for s in reversed(self.scopes):
                if s.kind != "comp":
                    s.bound.add(t.id)
                    return
        elif isinstance(t, (ast.Tuple, ast.List, ast.Starred)):
            self.bind_target(t)

    def bind_target(self, t: ast.expr) -> None:
        if isinstance(t, ast.Name):
            self.bind(t.id)
        elif isinstance(t, ast.Starred):
            self.bind_target(t.value)
        elif isinstance(t, (ast.Tuple, ast.List)):
            for el in t.elts:
                self.bind_target(el)

    def is_bound(self, name: str) -> bool:
        in_func = False
        nonlocal_only = False
        for i in range(len(self.scopes) - 1, 0, -1):
            s = self.scopes[i]
            if name in s.globals:
                return name in self.scopes[0].bound
            if name in s.nonlocals:
                in_func = True
                nonlocal_only = True
                continue
            if s.kind == "class" and in_func:
                continue  # funcs can't see class-body names
            if name in s.bound:
                return True
            if s.kind in ("func", "comp"):
                in_func = True
        if nonlocal_only:
            return False  # nonlocal never reaches module scope
        return name in self.scopes[0].bound

    def unbound(self, name: str, lineno: int) -> None:
        self.graph.symbols.append(SymbolEdge(self.modname, name, lineno))

    def unresolved(self, lineno: int, name: str, kind: str, detail: str) -> None:
        self.graph.unresolved.append(
            Unresolved(self.relfile, lineno, name, kind, detail)
        )

    def edge_kind(self, ctx: _Ctx) -> str:
        if ctx.type_checking:
            return "type_checking"
        if ctx.in_try:
            return "conditional"
        return "static"

    def do_import(self, node: ast.Import, ctx: _Ctx) -> None:
        for a in node.names:
            self.graph.imports.append(
                ImportEdge(
                    importer=self.modname,
                    module=a.name,
                    names=((a.name, a.asname),),
                    level=0,
                    kind=self.edge_kind(ctx),
                    lineno=node.lineno,
                )
            )
            self.bind(a.asname or a.name.split(".")[0])

    def do_importfrom(self, node: ast.ImportFrom, ctx: _Ctx) -> None:
        pkg = self.info.name if self.info.is_pkg_init else self.info.package
        module = resolve_from(pkg, self.info.is_pkg_init, node.level, node.module)
        star = any(a.name == "*" for a in node.names)
        names = tuple((a.name, a.asname) for a in node.names if a.name != "*")
        self.graph.imports.append(
            ImportEdge(
                importer=self.modname,
                module=module,
                names=names,
                level=node.level,
                kind=self.edge_kind(ctx),
                lineno=node.lineno,
            )
        )
        for a in node.names:
            if a.name != "*":
                self.bind(a.asname or a.name)
        if star:
            self.unresolved(
                node.lineno, "*", "star_import", f"from {module} import *"
            )
            for n in sorted(self.all_names.get(module, ())):
                self.bind(n)
                if module in self.mods:
                    self.graph.imports.append(
                        ImportEdge(
                            importer=self.modname,
                            module=module,
                            names=((n, None),),
                            level=node.level,
                            kind=self.edge_kind(ctx),
                            lineno=node.lineno,
                        )
                    )

    def do_call(self, node: ast.Call) -> None:
        f = node.func
        fname = ""
        if isinstance(f, ast.Name):
            fname = f.id
        elif isinstance(f, ast.Attribute):
            fname = f.attr
        if fname in ("__import__", "import_module"):
            arg = node.args[0] if node.args else None
            lit = _lit_str(arg) if arg is not None else None
            if lit is not None:
                self.graph.imports.append(
                    ImportEdge(
                        importer=self.modname,
                        module=lit,
                        names=((lit, None),),
                        level=0,
                        kind="dynamic",
                        lineno=node.lineno,
                    )
                )
            elif arg is not None:
                self.unresolved(
                    node.lineno, fname, "dynamic_import", f"{fname}() of non-literal"
                )
        elif fname == "getattr" and len(node.args) >= 2:
            if _lit_str(node.args[1]) is None:
                self.unresolved(
                    node.lineno,
                    "getattr",
                    "getattr_dynamic",
                    "getattr() with non-literal name",
                )

    def visit(self, node: ast.AST, ctx: _Ctx) -> None:
        if isinstance(node, ast.Import):
            self.do_import(node, ctx)
            return
        if isinstance(node, ast.ImportFrom):
            self.do_importfrom(node, ctx)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                self.visit(dec, ctx.child())
            for d in node.args.defaults:
                self.visit(d, ctx.child())
            for d in node.args.kw_defaults:
                if d is not None:
                    self.visit(d, ctx.child())
            for a in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
                if a.annotation is not None:
                    self.visit(a.annotation, ctx.child())
            if node.args.vararg and node.args.vararg.annotation is not None:
                self.visit(node.args.vararg.annotation, ctx.child())
            if node.args.kwarg and node.args.kwarg.annotation is not None:
                self.visit(node.args.kwarg.annotation, ctx.child())
            if node.returns is not None:
                self.visit(node.returns, ctx.child())
            self.bind(node.name)
            scope = _Scope("func")
            args = node.args
            for a in (*args.posonlyargs, *args.args, *args.kwonlyargs):
                scope.bound.add(a.arg)
            if args.vararg:
                scope.bound.add(args.vararg.arg)
            if args.kwarg:
                scope.bound.add(args.kwarg.arg)
            self.scopes.append(scope)
            for stmt in node.body:
                self.visit(stmt, ctx.child())
            self.scopes.pop()
            return
        if isinstance(node, ast.ClassDef):
            for dec in node.decorator_list:
                self.visit(dec, ctx.child())
            for b in node.bases:
                self.visit(b, ctx.child())
            for kw in node.keywords:
                self.visit(kw.value, ctx.child())
            self.bind(node.name)
            self.scopes.append(_Scope("class"))
            for stmt in node.body:
                self.visit(stmt, ctx.child())
            self.scopes.pop()
            return
        if isinstance(node, ast.Lambda):
            scope = _Scope("func")
            args = node.args
            for a in (*args.posonlyargs, *args.args, *args.kwonlyargs):
                scope.bound.add(a.arg)
            if args.vararg:
                scope.bound.add(args.vararg.arg)
            if args.kwarg:
                scope.bound.add(args.kwarg.arg)
            for d in args.defaults:
                self.visit(d, ctx.child())
            for d in args.kw_defaults:
                if d is not None:
                    self.visit(d, ctx.child())
            self.scopes.append(scope)
            self.visit(node.body, ctx.child())
            self.scopes.pop()
            return
        if isinstance(node, ast.If):
            self.visit(node.test, ctx.child())
            tc = ctx.type_checking or _type_check_test(node.test)
            body_ctx = _Ctx(tc, ctx.in_try)
            for stmt in node.body:
                self.visit(stmt, body_ctx)
            for stmt in node.orelse:
                self.visit(stmt, ctx.child())
            return
        if isinstance(node, ast.Try) or (
            hasattr(ast, "TryStar") and isinstance(node, ast.TryStar)
        ):
            cond = ctx.in_try or _catches_import_error(node)
            body_ctx = _Ctx(ctx.type_checking, cond)
            for stmt in node.body:
                self.visit(stmt, body_ctx)
            for h in node.handlers:
                if h.type is not None:
                    self.visit(h.type, ctx.child())
                if h.name:
                    self.bind(h.name)
                for stmt in h.body:
                    self.visit(stmt, ctx.child())
            for stmt in node.orelse:
                self.visit(stmt, ctx.child())
            for stmt in node.finalbody:
                self.visit(stmt, ctx.child())
            return
        if isinstance(node, (ast.For, ast.AsyncFor)):
            self.visit(node.iter, ctx.child())
            self.bind_target(node.target)
            for stmt in node.body:
                self.visit(stmt, ctx.child())
            for stmt in node.orelse:
                self.visit(stmt, ctx.child())
            return
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                self.visit(item.context_expr, ctx.child())
                if item.optional_vars is not None:
                    self.bind_target(item.optional_vars)
            for stmt in node.body:
                self.visit(stmt, ctx.child())
            return
        if isinstance(node, ast.Assign):
            self.visit(node.value, ctx.child())
            for t in node.targets:
                self.bind_target(t)
            return
        if isinstance(node, ast.AnnAssign):
            if node.value is not None:
                self.visit(node.value, ctx.child())
            self.visit(node.annotation, ctx.child())
            self.bind_target(node.target)
            return
        if isinstance(node, ast.AugAssign):
            self.visit(node.value, ctx.child())
            if isinstance(node.target, ast.Name):
                if not self.is_bound(node.target.id):
                    self.bind(node.target.id)
            else:
                self.visit(node.target, ctx.child())
            return
        if isinstance(node, ast.NamedExpr):
            self.visit(node.value, ctx.child())
            self.bind_walrus(node.target)
            return
        if isinstance(node, ast.Delete):
            for t in node.targets:
                self.visit(t, ctx.child())
            return
        if isinstance(node, ast.Match):
            self.visit(node.subject, ctx.child())
            for case in node.cases:
                self.visit(case.pattern, ctx.child())
                pat_names: set[str] = set()
                _pattern_names(case.pattern, pat_names)
                for n in pat_names:
                    self.bind(n)
                if case.guard is not None:
                    self.visit(case.guard, ctx.child())
                for stmt in case.body:
                    self.visit(stmt, ctx.child())
            return
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            inner = _Scope("comp")
            self.scopes.append(inner)
            for comp in node.generators:
                self.visit(comp.iter, ctx.child())
                bound: set[str] = set()
                _collect_target_names(comp.target, bound)
                inner.bound |= bound
                for cond in comp.ifs:
                    self.visit(cond, ctx.child())
            if isinstance(node, ast.DictComp):
                self.visit(node.key, ctx.child())
                self.visit(node.value, ctx.child())
            else:
                self.visit(node.elt, ctx.child())
            self.scopes.pop()
            return
        if isinstance(node, ast.Global):
            self.scopes[-1].globals.update(node.names)
            return
        if isinstance(node, ast.Nonlocal):
            self.scopes[-1].nonlocals.update(node.names)
            return
        if isinstance(node, ast.Call):
            self.do_call(node)
            self.visit(node.func, ctx.child())
            for a in node.args:
                self.visit(a, ctx.child())
            for kw in node.keywords:
                self.visit(kw.value, ctx.child())
            return
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                if not self.is_bound(node.id) and node.id not in _BUILTINS:
                    self.unbound(node.id, node.lineno)
            else:
                self.bind(node.id)
            return
        for child in ast.iter_child_nodes(node):
            self.visit(child, ctx.child())


def _collect_target_names(t: ast.expr, out: set[str]) -> None:
    if isinstance(t, ast.Name):
        out.add(t.id)
    elif isinstance(t, ast.Starred):
        _collect_target_names(t.value, out)
    elif isinstance(t, (ast.Tuple, ast.List)):
        for el in t.elts:
            _collect_target_names(el, out)


def _pattern_names(p: ast.AST, out: set[str]) -> None:
    name = getattr(p, "name", None)
    if isinstance(name, str):
        out.add(name)
    rest = getattr(p, "rest", None)
    if isinstance(rest, str):
        out.add(rest)
    for c in ast.iter_child_nodes(p):
        if isinstance(c, ast.pattern):
            _pattern_names(c, out)


def _analyze_module(
    modname: str,
    tree: ast.Module,
    mods: dict[str, ModuleInfo],
    graph: ModuleGraph,
    all_names: dict[str, set[str]],
    root: Path,
) -> None:
    w = _Walker(modname, mods[modname], mods, graph, all_names, root)
    for stmt in tree.body:
        w.visit(stmt, _Ctx())
