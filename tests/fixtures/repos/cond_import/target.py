try:
    import fast_impl
except ImportError:
    import slow_impl as fast_impl


def go() -> int:
    return fast_impl.go()
