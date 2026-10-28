"""Lua language specification."""

from __future__ import annotations

import re
from yoink.lang import LangSpec

LUA_STDLIB = frozenset({
    "coroutine", "package", "string", "utf8", "table", "math", "io", "os", "debug", "bit", "ffi", "jit",
})

LUA_SPEC = LangSpec(
    id="lua",
    name="Lua",
    extensions=(".lua",),
    std_libs=LUA_STDLIB,
    entry_files=("init.lua", "main.lua", "src/init.lua", "src/main.lua"),
    package_manifests=("rockspec",),
    license_files=("LICENSE",),
    import_res=(
        re.compile(r"""\b(?:require|dofile|loadfile)\s*(?:\(\s*)?['"]([^'"]+)['"]\s*\)?""", re.MULTILINE),
    ),
    comment_res=(r"--\[\[[\s\S]*?\]\]", r"--[^\n]*"),
    package_manager="luarocks",
)
