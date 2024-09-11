from guppylang.decorator import guppy
from guppylang.module import GuppyModule
from guppylang.prelude.builtins import owned
from guppylang.prelude.quantum import qubit, quantum

module = GuppyModule("test")
module.load_all(quantum)


@guppy.declare(module)
def foo(q: qubit) -> None: ...


@guppy.struct(module)
class MyImmutableContainer:
    q: qubit

    @guppy.declare(module)
    def __getitem__(self: "MyImmutableContainer", idx: int) -> qubit: ...


@guppy(module)
def test(c: MyImmutableContainer) -> MyImmutableContainer:
    foo(c[0])
    return c


module.compile()
