from __future__ import annotations

from yoink.closure import compute_closure
from yoink.graph.base import build_generic_module_map, build_graph, resolve_target
from yoink.gitignore import load_ignore
from yoink.lang import get_spec
from yoink.lang.detect import detect_language
from yoink.lang.resolve import find_symbol_candidates


def _graph(root, lang):
    ig = load_ignore(root)
    mods = build_generic_module_map(root, ig, get_spec(lang))
    return mods, build_graph(root, lang, mods)


def test_detect(fixture):
    assert detect_language(fixture("csharp_lib")) == "csharp"
    assert detect_language(fixture("jsts_lib")) == "jsts"
    assert detect_language(fixture("go_lib")) == "go"
    assert detect_language(fixture("rust_lib")) == "rust"


def test_csharp_graph(fixture):
    mods, g = _graph(fixture("csharp_lib"), "csharp")
    raw = {e.module for e in g.imports}
    assert any("Acme.Data" in m or "Store" in m for m in raw | set(mods))


def test_jsts_relative_external(fixture):
    mods, g = _graph(fixture("jsts_lib"), "jsts")
    raw = {e.module for e in g.imports}
    assert "lodash" in raw
    assert any("./b" in m or "b" == m.split("/")[-1] for m in raw)


def test_jsts_import_type_kind(fixture):
    mods, g = _graph(fixture("jsts_lib"), "jsts")
    kinds = {e.module: e.kind for e in g.imports}
    assert any(k == "type_checking" for k in kinds.values())


def test_go_stdlib(fixture):
    mods, g = _graph(fixture("go_lib"), "go")
    raw = {e.module for e in g.imports}
    assert "fmt" in raw


def test_rust_mod_use(fixture):
    mods, g = _graph(fixture("rust_lib"), "rust")
    raw = {e.module for e in g.imports}
    assert any("inner" in m or "other" in m or "crate" in m for m in raw)


def test_find_symbol_candidates(fixture):
    root = fixture("csharp_lib")
    spec = get_spec("csharp")
    mods = build_generic_module_map(root, load_ignore(root), spec)
    cands = find_symbol_candidates(root, mods, spec, "Yoink")
    assert cands and cands[0][1] >= 60


def test_generic_closure(fixture):
    root = fixture("csharp_lib")
    spec = get_spec("csharp")
    mods, g = _graph(root, "csharp")
    tmod, tsym = resolve_target(mods, g.defns, "Yoink", "csharp")
    c = compute_closure(g, mods, tmod, tsym, max_depth=12, source_root=root, spec=spec)
    assert len(c.modules) >= 2
    assert any(d.name == "Newtonsoft.Json" for d in c.external)
    assert any(s.startswith("System") or s == "System" for s in c.stdlib)


def test_generic_closure_jsts(fixture):
    root = fixture("jsts_lib")
    spec = get_spec("jsts")
    mods, g = _graph(root, "jsts")
    tmod, tsym = resolve_target(mods, g.defns, "a", "jsts")
    c = compute_closure(g, mods, tmod, tsym, max_depth=12, source_root=root, spec=spec)
    assert any(d.name == "lodash" for d in c.external)
    assert len(c.modules) >= 2
