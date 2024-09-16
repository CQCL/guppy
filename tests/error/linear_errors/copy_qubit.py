import guppylang.prelude.quantum as quantum
from guppylang.decorator import guppy
from guppylang.module import GuppyModule
from guppylang.prelude.builtins import owned
from guppylang.prelude.quantum import qubit


module = GuppyModule("test")
module.load_all(quantum)


@guppy(module)
def foo(q: qubit @owned) -> tuple[qubit, qubit]:
    return q, q


module.compile()