from __future__ import annotations

from yoink.graph.python_ast import build_python_graph
from yoink.modulemap import build_module_map


def _graph(root):
    mods = build_module_map(root)
    return build_python_graph(root, mods)


def test_static_imports(make_repo):
    root = make_repo({"a.py": "import b\n", "b.py": ""})
    g = _graph(root)
    assert any(e.importer == "a" and e.module == "b" for e in g.imports)


def test_relative_import_levels(make_repo):
    root = make_repo(
        {
            "pkg/__init__.py": "",
            "pkg/mod.py": "from .sib import y\nfrom . import sib\n",
            "pkg/sib.py": "from ..other import z\n",
            "other.py": "z = 1\n",
        }
    )
    g = _graph(root)
    mods = {e.module for e in g.imports}
    assert "pkg.sib" in mods
    assert "other" in mods


def test_type_checking_kind(make_repo):
    root = make_repo(
        {
            "m.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import heavy\n",
            "heavy.py": "",
        }
    )
    g = _graph(root)
    e = [e for e in g.imports if e.module == "heavy"]
    assert e and e[0].kind == "type_checking"


def test_conditional_kind(make_repo):
    root = make_repo(
        {"m.py": "try:\n    import fast\nexcept ImportError:\n    pass\n", "fast.py": ""}
    )
    g = _graph(root)
    e = [e for e in g.imports if e.module == "fast"]
    assert e and e[0].kind == "conditional"


def test_dunder_import_literal_vs_var(make_repo):
    root = make_repo(
        {
            "m.py": "x = __import__('helper')\ny = __import__(name)\n",
            "helper.py": "",
        }
    )
    g = _graph(root)
    assert any(e.module == "helper" for e in g.imports)
    assert any(u.kind == "dynamic_import" for u in g.unresolved)


def test_getattr_dynamic(make_repo):
    root = make_repo({"m.py": "v = getattr(obj, attr)\n"})
    g = _graph(root)
    assert any(u.kind == "getattr_dynamic" for u in g.unresolved)


def test_star_import_resolves_all(make_repo):
    root = make_repo(
        {
            "pool.py": "__all__=['f1']\ndef f1(): pass\ndef _h(): pass\n",
            "m.py": "from pool import *\n",
        }
    )
    g = _graph(root)
    assert any(u.kind == "star_import" for u in g.unresolved)


def test_unbound_name_symbol_edge(make_repo):
    root = make_repo({"m.py": "def f():\n    return undefined_thing\n"})
    g = _graph(root)
    assert any(s.name == "undefined_thing" for s in g.symbols)


def test_defn_table(make_repo):
    root = make_repo(
        {"m.py": "class C: pass\ndef f(): pass\nX = 1\nimport os\n"}
    )
    g = _graph(root)
    names = {d.name: d.kind for d in g.defns["m"]}
    assert names["C"] == "class" and names["f"] == "func" and names["X"] == "assign"
    assert names["os"] == "import"


def test_reexport_binding(fixture):
    g = _graph(fixture("reexport_chain"))
    names = {d.name for d in g.defns["pkg.b"]}
    assert "leaf" in names
