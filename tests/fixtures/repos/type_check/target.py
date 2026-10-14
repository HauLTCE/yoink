from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import heavy


def work() -> int:
    # heavy only matters to the type checker
    return 7
