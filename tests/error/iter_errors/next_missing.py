from guppylang.decorator import guppy
from guppylang.module import GuppyModule
from guppylang.tys.ty import NoneType


module = GuppyModule("test")


@guppy.type(module, NoneType().to_hugr())
class MyIter:
    """An iterator that is missing the `__next__` method."""

    @guppy.declare(module)
    def __hasnext__(self: "MyIter") -> tuple[bool, "MyIter"]:
        ...

    @guppy.declare(module)
    def __end__(self: "MyIter") -> None:
        ...


@guppy.type(module, NoneType().to_hugr())
class MyType:
    """Type that produces the iterator above."""

    @guppy.declare(module)
    def __iter__(self: "MyType") -> MyIter:
        ...


@guppy(module)
def test(x: MyType) -> None:
    for _ in x:
        pass


module.compile()
