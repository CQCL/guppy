from tests.util import compile_guppy


def test_arith_basic(validate):
    @compile_guppy
    def add(x: int, y: int) -> int:
        return x + y

    validate(add)


def test_constant(validate):
    @compile_guppy
    def const() -> float:
        return 42.0

    validate(const)


def test_aug_assign(validate):
    @compile_guppy
    def add(x: int) -> int:
        x += 1
        return x

    validate(add)


def test_bool(validate):
    @compile_guppy
    def add(x: bool, y: bool) -> int:
        return x + y

    validate(add)


def test_float_coercion(validate):
    @compile_guppy
    def coerce(x: int, y: float, z: bool) -> float:
        return x * y + z

    validate(coerce)


def test_arith_big(validate):
    @compile_guppy
    def arith(x: int, y: float, z: int) -> bool:
        a = x // y + 3 * z
        b = -8 >= a > 5 or (x * y == 0 and a % 3 < x)
        return b

    validate(arith)


def test_shortcircuit_assign1(validate):
    @compile_guppy
    def foo(x: bool, y: int) -> bool:
        if (z := x) and y > 0:
            return z
        return not z

    validate(foo)


def test_shortcircuit_assign2(validate):
    @compile_guppy
    def foo(x: bool, y: int) -> bool:
        if y > 0 and (z := x):
            return z
        return False

    validate(foo)


def test_shortcircuit_assign3(validate):
    @compile_guppy
    def foo(x: bool, y: int) -> bool:
        if (z := x) or y > 0:
            return z
        return z

    validate(foo)


def test_shortcircuit_assign4(validate):
    @compile_guppy
    def foo(x: bool, y: int) -> bool:
        if y > 0 or (z := x):
            return False
        return z

    validate(foo)
