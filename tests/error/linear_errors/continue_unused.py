from guppy.compiler import GuppyModule
from tests.error.util import guppy, qubit


module = GuppyModule("test")


@module.declare
def new_qubit() -> qubit:
    pass


@module.declare
def measure() -> bool:
    pass


@module
def foo(i: int) -> bool:
    b = False
    while i > 0:
        q = new_qubit()
        if i % 10 == 0:
            break
        i -= 1
        b ^= measure(q)
    return b


module.compile(True)