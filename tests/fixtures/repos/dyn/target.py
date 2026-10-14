"""Every dynamic trick in the book. Each should land in unresolved."""

import importlib

name = "plugin_a"
prefix = "mod"
obj = object()
attr = "thing"

mod = __import__(name)
dyn = importlib.import_module(f"{prefix}_x")
val = getattr(obj, attr)

# literals DO resolve
lit = importlib.import_module("helper")


def main() -> int:
    from helper import leaf

    return leaf()
