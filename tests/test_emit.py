from __future__ import annotations

import ast
import zipfile
from pathlib import Path

from yoink.closure import compute_closure
from yoink.emit import emit_bundle, emit_flat, emit_zip
from yoink.graph.base import build_graph, build_generic_module_map, resolve_target
from yoink.graph.python_ast import build_python_graph
from yoink.gitignore import load_ignore
from yoink.lang import get_spec
from yoink.modulemap import build_module_map


def _py(root, target, max_depth=12):
    mods = build_module_map(root)
    g = build_python_graph(root, mods)
    tmod, tsym = resolve_target(mods, g.defns, target, "python")
    c = compute_closure(g, mods, tmod, tsym, max_depth=max_depth, source_root=root, target=target)
    return g, c


def test_bundle_layout(fixture, tmp_path):
    root = fixture("reexport_chain")
    g, c = _py(root, "leaf")
    out = tmp_path / "out"
    r = emit_bundle(g, c, root, out)
    names = {p.name for p in r.files}
    assert "c.py" in names and "__init__.py" in names
    assert any("__init__.py" in str(p) and "pkg" in str(p) for p in r.files)


def test_bundle_init_synthesis(fixture, tmp_path):
    root = fixture("reexport_chain")
    g, c = _py(root, "leaf")
    out = tmp_path / "out"
    emit_bundle(g, c, root, out)
    assert (out / "pkg" / "__init__.py").exists()


def test_flat_parses_and_runs(fixture, tmp_path):
    root = fixture("reexport_chain")
    g, c = _py(root, "leaf")
    out = tmp_path / "flat.py"
    emit_flat(g, c, root, out, target_module="pkg", target_symbol="leaf")
    src = out.read_text()
    ast.parse(src)
    ns: dict = {}
    exec(compile(src, str(out), "exec"), ns)
    assert ns["leaf"]() == 42


def test_flat_side_effects_wholesale(fixture, tmp_path):
    root = fixture("side_effects")
    g, c = _py(root, "run")
    out = tmp_path / "flat.py"
    r = emit_flat(g, c, root, out)
    assert any("side effect" in w.lower() or "wholesale" in w for w in r.warnings)


def test_flat_generic_concat(fixture, tmp_path):
    root = fixture("generic_flat")
    spec = get_spec("csharp")
    mods = build_generic_module_map(root, load_ignore(root), spec)
    g = build_graph(root, "csharp", mods)
    tmod, tsym = resolve_target(mods, g.defns, "Go", "csharp")
    c = compute_closure(g, mods, tmod, tsym, max_depth=12, source_root=root, spec=spec)
    out = tmp_path / "flat.cs"
    emit_flat(g, c, root, out, spec=spec, target_module=tmod, target_symbol=tsym)
    src = out.read_text()
    assert "====" in src
    assert "class One" in src and "class Two" in src
    assert src.count("using TwoNs") == 1 or "using TwoNs;" in src.split("class One")[0]


def test_zip(fixture, tmp_path):
    root = fixture("reexport_chain")
    g, c = _py(root, "leaf")
    out = tmp_path / "out"
    emit_bundle(g, c, root, out)
    (out / "yoink.manifest.json").write_text("{}")
    zp = emit_zip(out)
    assert zp.suffix == ".zip"
    with zipfile.ZipFile(zp) as z:
        assert "yoink.manifest.json" in z.namelist()
