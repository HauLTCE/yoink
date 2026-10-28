"""C# language specification."""

from __future__ import annotations

import re
from yoink.lang import LangSpec

CSHARP_STDLIB = frozenset({
    "System", "Microsoft.CSharp", "Microsoft.VisualBasic", "Microsoft.Win32",
})

CSHARP_SPEC = LangSpec(
    id="csharp",
    name="C#",
    extensions=(".cs",),
    std_libs=CSHARP_STDLIB,
    stdlib_prefixes=("System.", "System", "Microsoft.CSharp", "Microsoft.Win32"),
    entry_files=("Program.cs", "Startup.cs"),
    package_manifests=("Directory.Packages.props", "packages.config"),
    license_files=("LICENSE", "LICENSE.txt", "LICENSE.md"),
    import_res=(
        re.compile(
            r"""^\s*(?:global\s+)?using\s+(?:static\s+)?(?:[A-Za-z_][A-Za-z0-9_]*\s*=\s*)?([A-Za-z_][A-Za-z0-9_.]*)\s*;""",
            re.MULTILINE,
        ),
    ),
    comment_res=(r"//[^\n]*", r"/\*[\s\S]*?\*/"),
    package_manager="dotnet",
    verify_command="dotnet build",
    lockfiles=("packages.lock.json",),
)
