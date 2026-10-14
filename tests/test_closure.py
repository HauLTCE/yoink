from __future__ import annotations

from yoink.closure import compute_closure
from yoink.graph.base import resolve_target
from yoink.graph.python_ast import build_python_graph
from yoink.modulemap import build_module_map


def _closure(root, target, max_depth=12):
    mods = build_module_map(root)
    g = build_python_graph(root, mods)
    tmod, tsym = resolve_target(mods, g.defns, target, "python")
    return g, compute_closure(
        g, mods, tmod, tsym, max_depth=max_depth, source_root=root, target=target
    )


def test_reexport_chain_pulls_all(fixture):
    g, c = _closure(fixture("reexport_chain"), "leaf")
    assert {"pkg", "pkg.a", "pkg.b", "pkg.c"} <= c.modules


def test_type_checking_not_pulled(fixture):
    g, c = _closure(fixture("type_check"), "work")
    assert "heavy" not in c.modules


def test_conditional_pulled_with_warning(fixture):
    g, c = _closure(fixture("cond_import"), "target:go")
    assert "fast_impl" in c.modules and "slow_impl" in c.modules


def test_cycle_terminates(fixture):
    g, c = _closure(fixture("cycle"), "one")
    assert "m1" in c.modules and "m2" in c.modules


def test_depth_hit(fixture):
    g, c = _closure(fixture("deep_pkg"), "top:deep_leaf", max_depth=1)
    assert c.depth_hit


def test_external_dep_versions(fixture):
    g, c = _closure(fixture("external_dep"), "fetch")
    ext = {d.name: d for d in c.external}
    assert "requests" in ext and ext["requests"].version == "2.31.0"
    assert any(d.name.lower() in ("yaml", "pyyaml") for d in c.external)


def test_stdlib_classification(fixture):
    g, c = _closure(fixture("stdlib_mix"), "work")
    assert {"os", "pathlib", "collections", "json"} <= c.stdlib


def test_gitignored_unresolved(fixture):
    g, c = _closure(fixture("gitignored"), "main")
    assert not any("secret_dep" in m for m in c.modules)
    assert any(u.name == "secret_dep" for u in c.unresolved)


def test_unresolved_dynamic(fixture):
    g, c = _closure(fixture("dyn"), "main")
    kinds = {u.kind for u in c.unresolved}
    assert "dynamic_import" in kinds and "getattr_dynamic" in kinds
    assert "helper" in c.modules


def test_star_import(fixture):
    g, c = _closure(fixture("star_wars"), "go")
    assert "pool" in c.modules
    assert any(u.kind == "star_import" for u in c.unresolved)
