from guppylang.decorator import guppy
from guppylang.module import GuppyModule
from guppylang.prelude.builtins import owned
from guppylang.prelude.quantum import qubit, quantum

module = GuppyModule("test")
module.load_all(quantum)


@guppy.declare(module)
def foo(q1: qubit, q2: qubit @owned) -> qubit: ...


@guppy(module)
def test(q1: qubit @owned, q2: qubit @owned) -> tuple[qubit, qubit]:
    q1 = foo(q1, q2)
    return q1, q2


module.compile()
