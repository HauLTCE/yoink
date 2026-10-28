"""Bundle emit: copy pulled files preserving repo layout + synthesized inits and path safety."""

from __future__ import annotations

import shutil
from pathlib import Path

from yoink.errors import EmitError
from yoink.model import Closure, EmitResult, ModuleGraph
from yoink.util import ensure_safe_write_path, find_source_root


def emit_bundle(
    graph: ModuleGraph,
    closure: Closure,
    source_root: Path,
    out_dir: Path,
    *,
    granularity: str = "file",
    force: bool = False,
) -> EmitResult:
    """Copy pulled modules under `out_dir`; synthesize missing `__init__.py` files."""
    source_root = Path(source_root).resolve()
    out_dir = Path(out_dir).resolve()
    if out_dir.exists() and any(out_dir.iterdir()) and not force:
        raise EmitError(f"output dir not empty: {out_dir} (pass force=True or --force to overwrite)")
    out_dir.mkdir(parents=True, exist_ok=True)

    real_root = find_source_root(source_root, language=graph.language)
    files: list[Path] = []
    warnings: list[str] = []

    pkg_dirs_needed: set[Path] = set()
    for name in sorted(closure.modules):
        info = graph.modules.get(name)
        if info is None:
            continue
        try:
            rel = info.path.resolve().relative_to(real_root)
        except ValueError:
            try:
                rel = info.path.resolve().relative_to(source_root)
            except ValueError:
                rel = Path(info.path.name)
        if any(part == ".." for part in rel.parts):
            raise EmitError(f"unsafe relative module path rejected: {rel}")

        dest = ensure_safe_write_path(out_dir / rel, out_dir)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(info.path, dest)
        files.append(dest)

        if graph.language == "python":
            d = rel.parent
            while str(d) not in (".", ""):
                pkg_dirs_needed.add(ensure_safe_write_path(out_dir / d, out_dir))
                d = d.parent

    if graph.language == "python":
        for d in sorted(pkg_dirs_needed):
            init = ensure_safe_write_path(d / "__init__.py", out_dir)
            if not init.exists():
                init.parent.mkdir(parents=True, exist_ok=True)
                init.write_text("# synthesized by yoink\n", encoding="utf-8")
                files.append(init)

    for e in graph.imports:
        if e.importer in closure.modules and e.kind == "conditional":
            warnings.append(f"conditional import {e.module} pulled from try/except")
    if granularity == "symbol":
        warnings.append("bundle stays file-granular; symbol granularity ignored")

    try:
        from yoink.acquire.license import find_license_file

        lic = find_license_file(source_root)
    except Exception:
        lic = None
    if lic is not None:
        dest_lic = ensure_safe_write_path(out_dir / lic.name, out_dir)
        if not dest_lic.exists():
            shutil.copy2(lic, dest_lic)
            files.append(dest_lic)

    return EmitResult(files=sorted(files), warnings=warnings, output_dir=out_dir)
