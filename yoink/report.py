"""Human-facing output: rich when present, plain print otherwise."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from yoink.errors import SymbolNotFoundError, YoinkError
from yoink.model import Closure, ExternalDep, Unresolved

try:
    from rich.console import Console
    from rich.table import Table
    from rich.tree import Tree

    _console = Console()
    _err_console = Console(stderr=True)
    _HAS_RICH = True
except ImportError:  # pragma: no cover - exercised on dep-less installs
    _console = None  # type: ignore[assignment]
    _err_console = None  # type: ignore[assignment]
    _HAS_RICH = False


def _emit(text: str, *, err: bool = False) -> None:
    if _HAS_RICH:
        (_err_console if err else _console).print(text)
    else:
        print(text, file=sys.stderr if err else sys.stdout)


def closure_to_dict(closure: Closure) -> dict:
    """JSON-safe view of a Closure for --json doctor/analyze output."""
    return {
        "target": closure.target,
        "language": closure.language,
        "resolution": closure.resolution,
        "modules": sorted(closure.modules),
        "stdlib": sorted(closure.stdlib),
        "external": [
            {"name": d.name, "version": d.version, "evidence": d.evidence}
            for d in closure.external
        ],
        "unresolved": [
            {
                "file": u.file,
                "line": u.lineno,
                "kind": u.kind,
                "name": u.name,
                "detail": u.detail,
            }
            for u in closure.unresolved
        ],
        "depth_hit": closure.depth_hit,
    }


def _module_tree(modules: list[str]) -> Any:
    if not _HAS_RICH:
        return None
    tree = Tree("[bold]modules[/bold]")
    seen: dict[str, Any] = {}
    for mod in modules:
        parts = mod.split(".") if "." in mod else mod.split("/")
        node = tree
        path = ""
        for part in parts:
            path = f"{path}.{part}" if path else part
            if path not in seen:
                seen[path] = node.add(part)
            node = seen[path]
    return tree


def print_doctor(
    closure: Closure, manifest_dict: dict | None = None, *, json_mode: bool = False
) -> None:
    """Render the doctor report: tree, externals, unresolved, warnings."""
    if json_mode:
        payload: dict[str, Any] = manifest_dict if manifest_dict is not None else closure_to_dict(closure)
        print(json.dumps(payload, indent=2))
        return

    _emit(f"[bold]target[/bold]: {closure.target}")
    _emit(f"[bold]language[/bold]: {closure.language}  (resolution: {closure.resolution})")

    mods = sorted(closure.modules)
    _emit(f"\n[bold]pulled modules[/bold] ({len(mods)}):")
    if _HAS_RICH:
        tree = _module_tree(mods)
        if tree is not None:
            _console.print(tree)
    else:
        for m in mods:
            depth = m.count(".") + m.count("/")
            print(f"  {'  ' * depth}{m}")

    if closure.stdlib:
        _emit(f"\n[bold]stdlib[/bold] ({len(closure.stdlib)}): {', '.join(sorted(closure.stdlib))}")

    _emit(f"\n[bold]external deps[/bold] ({len(closure.external)}):")
    if _HAS_RICH:
        table = Table(show_header=True, header_style="bold")
        table.add_column("name")
        table.add_column("version")
        table.add_column("evidence")
        for dep in closure.external:
            table.add_row(dep.name, dep.version or "-", dep.evidence or "-")
        _console.print(table)
    else:
        for dep in closure.external:
            ver = dep.version or "-"
            print(f"  {dep.name}  {ver}  ({dep.evidence})")

    if closure.unresolved:
        _emit(f"\n[bold yellow]unresolved[/bold yellow] ({len(closure.unresolved)}):")
        for u in closure.unresolved:
            loc = f"{u.file}:{u.lineno}" if u.lineno else u.file
            _emit(f"  {loc}  [{u.kind}] {u.name} — {u.detail}")

    if closure.depth_hit:
        _emit("\n[yellow]warning[/yellow]: max depth hit — closure truncated")

    if manifest_dict:
        warnings = manifest_dict.get("warnings") or []
        if warnings:
            _emit("\n[bold]warnings[/bold]:")
            for w in warnings:
                _emit(f"  - {w}")


def print_result(manifest: Any, out_path: Path | None) -> None:
    """One-screen summary after extract."""
    data = manifest.to_dict() if hasattr(manifest, "to_dict") else manifest
    mode = data.get("mode", "?")
    out = data.get("output") or {}
    files = out.get("files") or []
    lines = out.get("lines", 0)
    n_mods = len(data.get("modules") or [])
    n_ext = len(data.get("external_deps") or [])
    n_unr = len(data.get("unresolved") or [])
    verified = (data.get("verified") or {}).get("status", "not_run")

    _emit(f"[bold green]yoinked[/bold green] {data.get('source', {}).get('target', '?')}")
    _emit(f"  mode:      {mode}")
    if out_path is not None:
        _emit(f"  output:    {out_path}")
    _emit(f"  files:     {len(files)} ({lines} lines)")
    _emit(f"  modules:   {n_mods}")
    _emit(f"  external:  {n_ext}")
    _emit(f"  unresolved:{(' [yellow]' + str(n_unr) + '[/yellow]') if n_unr else f' {n_unr}'}")
    if verified != "not_run":
        _emit(f"  verified:  {verified}")
    for w in data.get("warnings") or []:
        _emit(f"  [yellow]warn[/yellow]: {w}")


def print_error(exc: BaseException) -> None:
    """Friendly error; SymbolNotFoundError gets candidate hints."""
    if isinstance(exc, SymbolNotFoundError):
        _emit(f"[bold red]error[/bold red]: symbol not found: {exc.symbol}", err=True)
        if exc.candidates:
            _emit("  did you mean:", err=True)
            for cand in exc.candidates:
                _emit(f"    - {cand}", err=True)
        return
    if isinstance(exc, YoinkError):
        _emit(f"[bold red]error[/bold red]: {exc}", err=True)
        return
    _emit(f"[bold red]error[/bold red] ({type(exc).__name__}): {exc}", err=True)


__all__ = [
    "closure_to_dict",
    "print_doctor",
    "print_result",
    "print_error",
]
