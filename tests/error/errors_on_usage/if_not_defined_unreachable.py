from tests.util import compile_guppy


@compile_guppy
def foo() -> int:
    if False:
        y = 1
    return y
