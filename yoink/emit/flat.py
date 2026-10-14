"""Flat emit: one self-contained file — python symbol slice or generic concat."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import TYPE_CHECKING

from yoink.closure import build_bindings
from yoink.errors import EmitError
from yoink.model import Closure, Defn, EmitResult, ModuleGraph
from yoink.slice import (
    module_has_side_effects,
    needed_defns,
    parse_module,
    topo_order,
)
from yoink.util import read_text

if TYPE_CHECKING:
    from yoink.lang import LangSpec


def emit_flat(
    graph: ModuleGraph,
    closure: Closure,
    source_root: Path,
    out_path: Path,
    *,
    spec: "LangSpec | None" = None,
    target_module: str | None = None,
    target_symbol: str | None = None,
) -> EmitResult:
    """Emit a single file: sliced defns for python, bannered concat otherwise."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if spec is not None and graph.language != "python":
        return _flat_generic(graph, closure, out_path, spec)
    return _flat_python(
        graph, closure, out_path, target_module, target_symbol
    )


# ---------------------------------------------------------------------------
# python


def _flat_python(
    graph: ModuleGraph,
    closure: Closure,
    out_path: Path,
    target_module: str | None,
    target_symbol: str | None,
) -> EmitResult:
    order = topo_order(graph, closure.modules, target_module)
    bindings = build_bindings(graph, graph.modules)
    warnings: list[str] = []

    trees: dict[str, ast.Module] = {}
    sources: dict[str, str] = {}
    for mod in order:
        info = graph.modules[mod]
        try:
            text = info.path.read_bytes().decode("utf-8", errors="replace")
        except OSError as e:
            raise EmitError(f"cannot read {info.path}: {e}") from e
        sources[mod] = text
        try:
            trees[mod] = ast.parse(text, filename=str(info.path))
        except SyntaxError as e:
            raise EmitError(f"{info.path}:{e.lineno}: {e.msg}") from e

    pulled_defn_names = {
        d.name for m in order for d in graph.defns.get(m, ())
    }

    import_lines: list[str] = []
    seen_imports: set[str] = set()
    sections: list[tuple[str, list[str]]] = []
    emitted: dict[str, str] = {}  # name -> first module that claimed it
    ns_rewrites: dict[str, str] = {}  # bound-module name -> inlined root

    for mod in order:
        tree = trees[mod]
        src_lines = sources[mod].splitlines()
        info = graph.modules[mod]
        if module_has_side_effects(tree):
            warnings.append(
                f"module-level side effects in {mod} pulled wholesale"
            )
            body = _strip_pulled_imports(sources[mod], info, closure.modules)
            sections.append((mod, body.splitlines()))
            emitted.setdefault("*", mod)
            continue

        needed = needed_defns(
            graph, closure, mod, bindings,
            target_symbol=target_symbol, target_module=target_module,
        )
        needed = _expand_needed(tree, needed, graph.defns.get(mod, ()))

        section: list[str] = []
        for stmt in tree.body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                continue  # module docstring
            if isinstance(stmt, ast.Import):
                # drop imports that resolve into the pulled set — but if the
                # module is still used as `x.attr`, rewrite uses to the inlined
                # name so the flat file actually runs
                keep = []
                for a in stmt.names:
                    bound = a.asname or a.name.split(".")[0]
                    resolved = _resolved_in(a.name, closure.modules)
                    if resolved is None:
                        keep.append(a)
                    elif _name_used_as_namespace(tree, bound):
                        ns_rewrites[bound] = ""
                if keep:
                    imp = stmt if len(keep) == len(stmt.names) else ast.Import(names=keep)
                    line = ast.unparse(imp)
                    if line not in seen_imports:
                        seen_imports.add(line)
                        import_lines.append(line)
                continue
            if isinstance(stmt, ast.ImportFrom):
                if stmt.module == "__future__":
                    line = ast.unparse(stmt)
                    if line not in seen_imports:
                        seen_imports.add(line)
                        import_lines.insert(0, line)
                    continue
                resolved = _resolve_from(info, stmt)
                if resolved in closure.modules:
                    for a in stmt.names:
                        if a.name != "*" and a.name not in pulled_defn_names:
                            warnings.append(
                                f"flat: '{a.name}' from {resolved} not found in pulled defns"
                            )
                    continue  # names are local now
                line = ast.unparse(stmt)
                if line not in seen_imports:
                    seen_imports.add(line)
                    import_lines.append(line)
                continue
            name = _stmt_name(stmt)
            if name is None:
                continue
            if name not in needed and name != "__all__":
                continue
            emit_name = name
            if name in emitted and emitted[name] != mod:
                emit_name = f"{name}__{mod.replace('.', '_')}"
                warnings.append(
                    f"name collision: {name} from {mod} renamed to {emit_name}"
                )
            else:
                emitted[name] = mod
            seg = _segment(src_lines, stmt)
            if emit_name != name:
                seg = _rename_first(seg, name, emit_name)
            for ns in ns_rewrites:
                # `ns.attr` -> `attr` now that the module is inlined flat
                seg = [re.sub(rf"\b{re.escape(ns)}\.", "", ln) for ln in seg]
            section.extend(seg)
        sections.append((mod, section))

    out: list[str] = []
    if import_lines:
        out.extend(import_lines)
        out.append("")
    first = True
    for mod, lines in sections:
        if not lines:
            continue
        if not first:
            out.append("")
        out.append(f"# ==== {mod} ====")
        out.append("")
        out.extend(lines)
        first = False
    out_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    return EmitResult(files=[out_path], warnings=warnings, output_dir=out_path.parent)


_IMPORT_LEAD: dict[str, tuple[str, ...]] = {
    "csharp": ("using ",),
    "jsts": ("import ", "export ", "const ", "var ", "let "),
    "rust": ("use ", "mod ", "extern crate"),
    "java": ("import ",),
    "cpp": ("#include", "# include", "#  include"),
    "ruby": ("require", "require_relative", "load "),
    "php": ("use ", "require", "include"),
}


def _name_used_as_namespace(tree: ast.Module, name: str) -> bool:
    """True when `name.attr` attribute access appears anywhere in the module."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == name
        ):
            return True
    return False


def _is_import_line(stripped: str, spec: "LangSpec") -> bool:
    """Line is a hoisted import only when it leads with the lang's import form."""
    lead = _IMPORT_LEAD.get(spec.id)
    if lead and not stripped.startswith(lead):
        return False
    if not stripped:
        return False
    return any(re.search(r, stripped) for r in spec.import_re)


def _resolve_from(info, stmt: ast.ImportFrom) -> str:
    from yoink.graph.python_ast import resolve_from

    pkg = info.name if info.is_pkg_init else info.package
    return resolve_from(pkg, info.is_pkg_init, stmt.level, stmt.module)


def _resolved_in(raw: str, pulled: set[str]) -> str | None:
    if raw in pulled:
        return raw
    parts = raw.split(".")
    for k in range(len(parts) - 1, 0, -1):
        cand = ".".join(parts[:k])
        if cand in pulled:
            return cand
    return None


def _filter_import(stmt: ast.Import, pulled: set[str]) -> ast.Import | None:
    """Drop aliases that resolve into the pulled set; keep the rest."""
    keep = [a for a in stmt.names if _resolved_in(a.name, pulled) is None]
    if not keep:
        return None
    if len(keep) == len(stmt.names):
        return stmt
    return ast.Import(names=keep)


def _stmt_name(stmt: ast.stmt) -> str | None:
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return stmt.name
    if isinstance(stmt, ast.Assign):
        for t in stmt.targets:
            if isinstance(t, ast.Name):
                return t.id
        return None
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        return stmt.target.id
    return None


def _segment(src_lines: list[str], stmt: ast.stmt) -> list[str]:
    end = stmt.end_lineno or stmt.lineno
    return src_lines[stmt.lineno - 1 : end]


def _rename_first(lines: list[str], old: str, new: str) -> list[str]:
    """Rename the binding occurrence on the def line; leave uses honest."""
    if not lines:
        return lines
    idx = 0
    for i, line in enumerate(lines):
        if re.match(rf"\s*(?:async\s+def|def|class)\s+{re.escape(old)}\b", line) or re.match(
            rf"\s*{re.escape(old)}\s*[:=]", line
        ):
            idx = i
            break
    lines[idx] = re.sub(rf"\b{re.escape(old)}\b", new, lines[idx], count=1)
    return lines


def _expand_needed(
    tree: ast.Module, needed: set[str], defns: list[Defn]
) -> set[str]:
    """Pull sibling defns referenced by name inside already-needed defns."""
    names_of = {d.name for d in defns}
    by_name: dict[str, ast.stmt] = {}
    for stmt in tree.body:
        n = _stmt_name(stmt)
        if n:
            by_name[n] = stmt
    work = set(needed)
    for _ in range(32):
        added: set[str] = set()
        for n in work:
            stmt = by_name.get(n)
            if stmt is None:
                continue
            for node in ast.walk(stmt):
                if isinstance(node, ast.Name) and node.id in names_of and node.id not in needed:
                    added.add(node.id)
                elif (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id in names_of
                    and node.value.id not in needed
                ):
                    added.add(node.value.id)
        if not added:
            break
        needed |= added
        work = added
    return needed


def _strip_pulled_imports(text: str, info, pulled: set[str]) -> str:
    """For wholesale modules: drop top-level import lines pointing into the pull."""
    lines = text.splitlines(keepends=True)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text
    drop: set[int] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.Import):
            if all(_resolved_in(a.name, pulled) for a in stmt.names):
                for ln in range(stmt.lineno, (stmt.end_lineno or stmt.lineno) + 1):
                    drop.add(ln)
        elif isinstance(stmt, ast.ImportFrom):
            if stmt.module == "__future__":
                continue
            if _resolve_from(info, stmt) in pulled:
                for ln in range(stmt.lineno, (stmt.end_lineno or stmt.lineno) + 1):
                    drop.add(ln)
    return "".join(l for i, l in enumerate(lines, 1) if i not in drop)


# ---------------------------------------------------------------------------
# generic


def _flat_generic(
    graph: ModuleGraph,
    closure: Closure,
    out_path: Path,
    spec: "LangSpec",
) -> EmitResult:
    order = topo_order(graph, closure.modules)
    sep = spec.flat_sep or "#"
    hoisted: list[str] = []
    seen: set[str] = set()
    out: list[str] = []
    warnings: list[str] = []
    for mod in order:
        info = graph.modules.get(mod)
        if info is None:
            continue
        text = read_text(info.path)
        body_lines: list[str] = []
        if spec.flat_import_first:
            in_import_block = False
            for line in text.splitlines():
                stripped = line.strip()
                if spec.id == "go":
                    # single `import "x"` hoists; `import (...)` block stays inline
                    if stripped.startswith("import ("):
                        in_import_block = True
                        body_lines.append(line)
                        continue
                    if in_import_block:
                        body_lines.append(line)
                        if stripped == ")":
                            in_import_block = False
                        continue
                    if stripped.startswith('import "') or re.match(
                        r'^import\s+\w+\s+"', stripped
                    ):
                        if stripped not in seen:
                            seen.add(stripped)
                            hoisted.append(stripped)
                        continue
                    body_lines.append(line)
                    continue
                if _is_import_line(stripped, spec):
                    if stripped not in seen:
                        seen.add(stripped)
                        hoisted.append(stripped)
                else:
                    body_lines.append(line)
        else:
            body_lines = text.splitlines()
        out.append(f"{sep} ==== {mod} ====")
        out.extend(body_lines)
        out.append("")
    final: list[str] = []
    if hoisted:
        final.extend(hoisted)
        final.append("")
    final.extend(out)
    out_path.write_text("\n".join(final).rstrip() + "\n", encoding="utf-8")
    return EmitResult(files=[out_path], warnings=warnings, output_dir=out_path.parent)
