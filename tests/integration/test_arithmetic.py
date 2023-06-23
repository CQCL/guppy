from guppy.compiler import guppy
from tests.integration.util import validate


def test_arith_basic():
    @guppy
    def add(x: int, y: int) -> int:
        return x + y

    validate(add)


def test_constant():
    @guppy
    def const() -> float:
        return 42.0

    validate(const)


def test_ann_assign():
    @guppy
    def add(x: int) -> int:
        x += 1
        return x

    validate(add)


def test_float_coercion():
    @guppy
    def coerce(x: int, y: float) -> float:
        return x * y

    validate(coerce)


def test_arith_big():
    @guppy
    def arith(x: int, y: float, z: int) -> bool:
        a = x ** y + 3 * z
        b = -8 >= a > 5 or (x * y == 0 and a % 3 < x)
        return b

    validate(arith)
