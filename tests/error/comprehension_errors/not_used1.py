import guppylang.prelude.quantum as quantum
from guppylang.decorator import guppy
from guppylang.module import GuppyModule
from guppylang.prelude.quantum import qubit
from guppylang.prelude.builtins import linst

module = GuppyModule("test")
module.load(quantum)


@guppy(module)
def foo(qs: linst[qubit]) -> list[int]:
    return [42 for q in qs]


module.compile()