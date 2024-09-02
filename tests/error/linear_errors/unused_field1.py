import guppylang.prelude.quantum as quantum
from guppylang.decorator import guppy
from guppylang.module import GuppyModule
from guppylang.prelude.quantum import qubit


module = GuppyModule("test")
module.load_all(quantum)


@guppy.struct(module)
class MyStruct:
    q: qubit
    x: int


@guppy(module)
def foo(s: MyStruct) -> int:
    return s.x


module.compile()
