"""AST-based dependency graph generator for Python."""

from __future__ import annotations

import ast
import builtins
from pathlib import Path

from yoink.errors import ParseError
from yoink.model import Defn, ImportEdge, ModuleGraph, ModuleInfo, SymbolEdge, Unresolved
from yoink.util import read_text

_BUILTINS = frozenset(dir(builtins)) | {
    "__name__",
    "__file__",
    "__doc__",
    "__package__",
    "__path__",
    "__spec__",
    "__all__",
    "__annotations__",
    "TYPE_CHECKING",
    "Self",
}
_EXC_NAMES = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}


def _decorator_names(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> tuple[str, ...]:
    names: list[str] = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            names.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            names.append(ast.unparse(dec))
        elif isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Name):
                names.append(dec.func.id)
            elif isinstance(dec.func, ast.Attribute):
                names.append(ast.unparse(dec.func))
    return tuple(names)


def _extract_assign_targets(target: ast.AST) -> list[str]:
    names: list[str] = []
    if isinstance(target, ast.Name):
        names.append(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            names.extend(_extract_assign_targets(elt))
    elif isinstance(target, ast.Starred):
        names.extend(_extract_assign_targets(target.value))
    return names


class _ASTVisitor(ast.NodeVisitor):
    def __init__(self, mod_name: str, file_path: Path) -> None:
        self.mod_name = mod_name
        self.file_path = file_path
        self.imports: list[ImportEdge] = []
        self.symbols: list[SymbolEdge] = []
        self.defns: list[Defn] = []
        self.unresolved: list[Unresolved] = []
        self._in_try_import = False
        self._depth = 0

    def visit_Try(self, node: ast.Try) -> None:
        catches_import_err = False
        for handler in node.handlers:
            if handler.type is None:
                catches_import_err = True
            elif isinstance(handler.type, ast.Name) and handler.type.id in _EXC_NAMES:
                catches_import_err = True
            elif isinstance(handler.type, ast.Tuple):
                if any(isinstance(e, ast.Name) and e.id in _EXC_NAMES for e in handler.type.elts):
                    catches_import_err = True
        prev = self._in_try_import
        if catches_import_err:
            self._in_try_import = True
        for stmt in node.body:
            self.visit(stmt)
        self._in_try_import = prev
        for handler in node.handlers:
            self.visit(handler)
        for stmt in node.orelse:
            self.visit(stmt)
        for stmt in node.finalbody:
            self.visit(stmt)

    def visit_Import(self, node: ast.Import) -> None:
        kind = "conditional" if self._in_try_import else "static"
        for alias in node.names:
            bound = alias.asname or alias.name.split(".")[0]
            self.imports.append(
                ImportEdge(
                    importer=self.mod_name,
                    module=alias.name,
                    names=((alias.name, alias.asname),),
                    level=0,
                    kind=kind,
                    lineno=node.lineno,
                )
            )
            if self._depth == 0:
                self.defns.append(
                    Defn(
                        name=bound,
                        kind="import",
                        lineno=node.lineno,
                        end_lineno=node.end_lineno or node.lineno,
                    )
                )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        kind = "conditional" if self._in_try_import else "static"
        pairs = tuple((a.name, a.asname) for a in node.names)
        self.imports.append(
            ImportEdge(
                importer=self.mod_name,
                module=node.module or "",
                names=pairs,
                level=node.level or 0,
                kind=kind,
                lineno=node.lineno,
            )
        )
        if self._depth == 0:
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound = alias.asname or alias.name
                self.defns.append(
                    Defn(
                        name=bound,
                        kind="import",
                        lineno=node.lineno,
                        end_lineno=node.end_lineno or node.lineno,
                    )
                )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._depth == 0:
            start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
            self.defns.append(
                Defn(
                    name=node.name,
                    kind="func",
                    lineno=start,
                    end_lineno=node.end_lineno or node.lineno,
                    decorators=_decorator_names(node),
                )
            )
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if self._depth == 0:
            start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
            self.defns.append(
                Defn(
                    name=node.name,
                    kind="func",
                    lineno=start,
                    end_lineno=node.end_lineno or node.lineno,
                    decorators=_decorator_names(node),
                )
            )
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self._depth == 0:
            start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
            self.defns.append(
                Defn(
                    name=node.name,
                    kind="class",
                    lineno=start,
                    end_lineno=node.end_lineno or node.lineno,
                    decorators=_decorator_names(node),
                )
            )
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._depth == 0:
            for tgt in node.targets:
                for name in _extract_assign_targets(tgt):
                    self.defns.append(
                        Defn(
                            name=name,
                            kind="assign",
                            lineno=node.lineno,
                            end_lineno=node.end_lineno or node.lineno,
                        )
                    )
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self._depth == 0:
            for name in _extract_assign_targets(node.target):
                self.defns.append(
                    Defn(
                        name=name,
                        kind="assign",
                        lineno=node.lineno,
                        end_lineno=node.end_lineno or node.lineno,
                    )
                )
        self.generic_visit(node)

    def visit_TypeAlias(self, node: ast. AST) -> None:  # Python 3.12+ `type X = ...`
        if self._depth == 0 and hasattr(node, "name") and isinstance(node.name, ast.Name):
            self.defns.append(
                Defn(
                    name=node.name.id,
                    kind="type",
                    lineno=getattr(node, "lineno", 1),
                    end_lineno=getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                )
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Detect dynamic imports: `__import__("pkg")` or `importlib.import_module("pkg")`
        func_name = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        if func_name in ("__import__", "import_module"):
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                dyn_mod = node.args[0].value
                self.imports.append(
                    ImportEdge(
                        importer=self.mod_name,
                        module=dyn_mod,
                        names=(),
                        level=0,
                        kind="dynamic",
                        lineno=node.lineno,
                    )
                )
            else:
                self.unresolved.append(
                    Unresolved(
                        file=self.file_path.name,
                        lineno=node.lineno,
                        name=func_name,
                        kind="dynamic_import",
                        detail=f"non-literal dynamic import via {func_name}()",
                    )
                )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id not in _BUILTINS:
            self.symbols.append(
                SymbolEdge(module=self.mod_name, name=node.id, lineno=node.lineno)
            )


def build_python_graph(root: Path, mods: dict[str, ModuleInfo]) -> ModuleGraph:
    """Parse all project `.py` files into ASTs to construct the complete ModuleGraph."""
    graph = ModuleGraph(language="python", modules=dict(mods))
    for mod_name, info in sorted(mods.items()):
        text = read_text(info.path)
        try:
            tree = ast.parse(text, filename=str(info.path))
        except SyntaxError as e:
            raise ParseError(f"syntax error in {info.path}: {e}") from e

        visitor = _ASTVisitor(mod_name, info.path)
        visitor.visit(tree)
        graph.imports.extend(visitor.imports)
        graph.symbols.extend(visitor.symbols)
        graph.defns[mod_name] = visitor.defns
        graph.unresolved.extend(visitor.unresolved)

    return graph
