"""Star-import pool — __all__ gates what `import *` sees."""

__all__ = ["f1", "f2"]


def f1() -> int:
    return 1


def f2() -> int:
    return 2


def _hidden() -> int:
    return 99
