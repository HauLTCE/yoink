"""Elixir language specification."""

from __future__ import annotations

import re
from yoink.lang import LangSpec

ELIXIR_STDLIB = frozenset({
    "Kernel", "Atom", "Base", "Bitwise", "Calendar", "Code", "Config", "Date",
    "DateTime", "DynamicSupervisor", "Enum", "Exception", "File", "Float",
    "Function", "GenEvent", "GenServer", "Inspect", "Integer", "IO", "Keyword",
    "List", "Logger", "Macro", "Map", "MapSet", "Module", "NaiveDateTime",
    "Node", "OptionParser", "PartitionSupervisor", "Path", "Port", "Process",
    "Protocol", "Range", "Record", "Regex", "Registry", "Set", "Stream",
    "String", "StringIO", "Supervisor", "System", "Task", "Time", "Tuple",
    "URI", "Version", " ExUnit", ":erlang", ":ets", ":crypto", ":math", ":timer",
})

ELIXIR_SPEC = LangSpec(
    id="elixir",
    name="Elixir",
    extensions=(".ex", ".exs"),
    std_libs=ELIXIR_STDLIB,
    stdlib_prefixes=("Elixir.Kernel", ":"),
    entry_files=("mix.exs", "lib/application.ex"),
    package_manifests=("mix.exs",),
    license_files=("LICENSE",),
    import_res=(
        re.compile(
            r"""^\s*(?:alias|import|require|use)\s+([A-Za-z0-9_.{},\s]+?)(?:,\s*(?:as|only|except):[^\n]*)?\s*$""",
            re.MULTILINE,
        ),
    ),
    comment_res=(r"#[^\n]*",),
    package_manager="mix",
    verify_command="mix compile",
    lockfiles=("mix.lock",),
)
