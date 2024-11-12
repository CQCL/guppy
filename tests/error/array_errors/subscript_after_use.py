import guppylang.std.quantum as quantum
from guppylang.decorator import guppy
from guppylang.module import GuppyModule
from guppylang.std.builtins import array, owned
from guppylang.std.quantum import qubit


module = GuppyModule("test")
module.load_all(quantum)


@guppy.declare(module)
def foo(qs: array[qubit, 42] @owned, q: qubit) -> array[qubit, 42]: ...


@guppy(module)
def main(qs: array[qubit, 42] @owned) -> array[qubit, 42]:
    return foo(qs, qs[0])


module.compile()
