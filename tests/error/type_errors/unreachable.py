from tests.util import compile_guppy


@compile_guppy
def foo(x: int) -> int:
    if False:
        # This code is unreachable, but we still type-check it
        return 1.0
    return 0
