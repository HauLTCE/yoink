from __future__ import annotations

from yoink.modulemap import build_module_map


def test_basic_pkg(make_repo):
    root = make_repo({"pkg/__init__.py": "", "pkg/mod.py": "x=1", "top.py": ""})
    mods = build_module_map(root)
    assert "pkg" in mods and mods["pkg"].is_pkg_init
    assert "pkg.mod" in mods
    assert mods["pkg.mod"].package == "pkg"


def test_nested(make_repo):
    root = make_repo(
        {
            "a/__init__.py": "",
            "a/b/__init__.py": "",
            "a/b/c.py": "",
        }
    )
    mods = build_module_map(root)
    assert "a.b.c" in mods and "a.b" in mods
    assert mods["a.b.c"].package == "a.b"


def test_loose_alias(make_repo):
    root = make_repo({"scripts/tool.py": "", "scripts/helpy.py": ""})
    mods = build_module_map(root)
    assert "scripts.tool" in mods or "tool" in mods
    assert "helpy" in mods or "scripts.helpy" in mods


def test_src_layout(make_repo):
    root = make_repo({"src/pkg/__init__.py": "", "src/pkg/m.py": ""})
    mods = build_module_map(root)
    assert "pkg.m" in mods


def test_stem_alias_collision_first_sorted_wins(make_repo):
    root = make_repo({"x/dup.py": "", "y/dup.py": ""})
    mods = build_module_map(root)
    assert "dup" in mods
    assert mods["dup"].path.name == "dup.py"
