"""Rust language specification."""

from __future__ import annotations

import re
from yoink.lang import LangSpec

RUST_STDLIB = frozenset({
    "std", "core", "alloc", "proc_macro", "test",
})

RUST_SPEC = LangSpec(
    id="rust",
    name="Rust",
    extensions=(".rs",),
    std_libs=RUST_STDLIB,
    stdlib_prefixes=("std::", "core::", "alloc::", "proc_macro::"),
    entry_files=("src/lib.rs", "src/main.rs", "lib.rs", "main.rs"),
    package_manifests=("Cargo.toml",),
    license_files=("LICENSE", "LICENSE-MIT", "LICENSE-APACHE"),
    import_res=(
        re.compile(r"""\b(?:pub(?:\([^)]*\))?\s+)?use\s+([^;]+);""", re.MULTILINE),
        re.compile(r"""^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*;""", re.MULTILINE),
        re.compile(r"""^\s*extern\s+crate\s+([A-Za-z_][A-Za-z0-9_]*)\s*;""", re.MULTILINE),
    ),
    comment_res=(r"//[^\n]*", r"/\*[\s\S]*?\*/"),
    package_manager="cargo",
    verify_command="cargo check",
    lockfiles=("Cargo.lock",),
)
