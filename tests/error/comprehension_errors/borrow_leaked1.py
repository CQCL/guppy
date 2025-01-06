import guppylang.std.quantum as quantum
from guppylang.decorator import guppy
from guppylang.module import GuppyModule
from guppylang.std.quantum import qubit
from guppylang.std.builtins import owned

module = GuppyModule("test")
module.load_all(quantum)


@guppy.declare(module)
def bar(q: qubit) -> int: ...


@guppy(module)
def foo(n: int, q: qubit @owned) -> list[int]:
    return [bar(q) for _ in range(n)]


module.compile()