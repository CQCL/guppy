from typing import Callable

from guppy.compiler import guppy, GuppyModule
from tests.integration.util import validate


def test_basic():
    module = GuppyModule("test")

    @module
    def bar(x: int) -> bool:
        return x > 0

    @module
    def foo() -> Callable[[int], bool]:
        return bar

    validate(module.compile())


def test_call_1():
    module = GuppyModule("test")

    @module
    def bar() -> bool:
        return False

    @module
    def foo() -> Callable[[], bool]:
        return bar

    @module
    def baz() -> bool:
        return foo()()

    validate(module.compile())


def test_call_2():
    module = GuppyModule("test")

    @module
    def bar(x: int) -> Callable[[int], None]:
        return bar(x - 1)

    @module
    def foo() -> Callable[[int], Callable[[int], None]]:
        return bar

    @module
    def baz(y: int) -> None:
        return foo()(y)(y)

    validate(module.compile())


def test_nested():
    @guppy
    def foo(x: int) -> Callable[[int], bool]:
        def bar(y: int) -> bool:
            return x > y

        return bar

    validate(foo)


def test_curry():
    module = GuppyModule("curry")

    @module
    def curry(f: Callable[[int, int], bool]) -> Callable[[int], Callable[[int], bool]]:
        def g(x: int) -> Callable[[int], bool]:
            def h(y: int) -> bool:
                return f(x, y)
            return h
        return g

    @module
    def uncurry(f: Callable[[int], Callable[[int], bool]]) -> Callable[[int, int], bool]:
        def g(x: int, y: int):
            return f(x)(y)
        return g

    @module
    def gt(x: int, y: int) -> bool:
        return x > y

    @module
    def main(x: int, y: int) -> None:
        curried = curry(gt)
        curried(x)(y)
        uncurried = uncurry(curried)
        uncurried(x, y)
        curry(uncurry(curry(gt)))(y)(x)


def test_y_combinator():
    module = GuppyModule("fib")

    @module
    def fac_(f: Callable[[int], int], n: int) -> int:
        if n == 0:
            return 1
        return n * f(n - 1)

    @module
    def Y(f: Callable[[Callable[[int], int], int], int]) -> Callable[[int], int]:
        def y(x: int) -> int:
            return f(Y(f), x)

        return y

    @module
    def fac(x: int) -> int:
        return Y(fac_)(x)

    validate(module.compile())
