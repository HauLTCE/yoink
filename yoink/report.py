"""Console output formatting using rich (with standard print fallback)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from yoink.model import Closure

try:
    from rich.console import Console
    from rich.table import Table

    _CONSOLE_OUT = Console(stderr=False)
    _CONSOLE_ERR = Console(stderr=True)
    _HAS_RICH = True
except Exception:
    _HAS_RICH = False


def _emit(text: str, *, err: bool = False) -> None:
    if _HAS_RICH:
        con = _CONSOLE_ERR if err else _CONSOLE_OUT
        con.print(text)
    else:
        stream = sys.stderr if err else sys.stdout
        print(text, file=stream)


def print_info(msg: str) -> None:
    _emit(f"[bold cyan]info:[/bold cyan] {msg}" if _HAS_RICH else f"info: {msg}")


def print_warn(msg: str) -> None:
    _emit(f"[bold yellow]warn:[/bold yellow] {msg}" if _HAS_RICH else f"warn: {msg}", err=True)


def print_error(err: Exception | str) -> None:
    _emit(f"[bold red]error:[/bold red] {err}" if _HAS_RICH else f"error: {err}", err=True)


def print_doctor(
    closure: Closure,
    manifest_dict: dict[str, Any] | None = None,
    *,
    json_mode: bool = False,
) -> None:
    """Print dependency closure diagnostics, external deps, and unresolved references."""
    if json_mode:
        payload = manifest_dict if manifest_dict is not None else {
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
                {"file": u.file, "lineno": u.lineno, "name": u.name, "kind": u.kind, "detail": u.detail}
                for u in closure.unresolved
            ],
        }
        print(json.dumps(payload, indent=2))
        return

    if _HAS_RICH:
        tbl = Table(title=f"yoink doctor: {closure.target} ({closure.language}, {closure.resolution})")
        tbl.add_column("Category", style="cyan", no_wrap=True)
        tbl.add_column("Count", justify="right", style="magenta")
        tbl.add_column("Items", style="white")
        tbl.add_row("Internal Modules", str(len(closure.modules)), ", ".join(sorted(closure.modules)) or "-")
        tbl.add_row("Stdlib", str(len(closure.stdlib)), ", ".join(sorted(closure.stdlib)) or "-")
        ext_str = ", ".join(
            f"{d.name}{f' ({d.version})' if d.version else ''}" for d in closure.external
        )
        tbl.add_row("External Packages", str(len(closure.external)), ext_str or "-")
        unres_str = ", ".join(f"{u.file}:{u.lineno} ({u.name})" for u in closure.unresolved)
        tbl.add_row("Unresolved", str(len(closure.unresolved)), unres_str or "-")
        _CONSOLE_OUT.print(tbl)
    else:
        print(f"Target: {closure.target} ({closure.language})")
        print(f"Modules ({len(closure.modules)}): {', '.join(sorted(closure.modules))}")
        print(f"Stdlib ({len(closure.stdlib)}): {', '.join(sorted(closure.stdlib))}")
        print(f"External ({len(closure.external)}): {', '.join(d.name for d in closure.external)}")
        print(f"Unresolved ({len(closure.unresolved)}): {', '.join(u.name for u in closure.unresolved)}")


def print_result(manifest: Any, out_path: Path | None, *, json_mode: bool = False) -> None:
    """Display summary of extracted files and line count."""
    d = manifest.to_dict() if hasattr(manifest, "to_dict") else dict(manifest)
    if json_mode:
        print(json.dumps(d, indent=2))
        return
    out_info = d.get("output", {})
    files = out_info.get("files", [])
    lines = out_info.get("lines", 0)
    dest_str = str(out_path) if out_path else "."
    print_info(
        f"Extracted {len(files)} file(s) ({lines} lines) for {d.get('source', {}).get('target', '')} -> {dest_str}"
    )
