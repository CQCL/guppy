from guppylang import GuppyModule, guppy, qubit
from guppylang.std import quantum
from guppylang.std.quantum import discard
from tests.util import compile_guppy


def test_var_defined1(validate):
    @compile_guppy
    def test() -> int:
        if True:
            x = 1
        return x

    validate(test)


def test_var_defined2(validate):
    @compile_guppy
    def test(b: bool) -> int:
        while True:
            if b:
                x = 1
                break
        return x

    validate(test)


def test_type_mismatch1(validate):
    @compile_guppy
    def test() -> int:
        if True:
            x = 1
        else:
            x = 1.0
        return x

    validate(test)


def test_type_mismatch2(validate):
    @compile_guppy
    def test() -> int:
        x = 1
        while False:
            x = 1.0
        return x

    validate(test)


def test_type_mismatch3(validate):
    @compile_guppy
    def test() -> int:
        x = 1
        if False and (x := 1.0):
            pass
        return x

    validate(test)


def test_unused_var_use1(validate):
    @compile_guppy
    def test() -> int:
        x = 1
        if True:
            return 0
        return x

    validate(test)


def test_unused_var_use2(validate):
    @compile_guppy
    def test() -> int:
        x = 1
        if not False:
            x = 1.0
            return 0
        return x

    validate(test)


def test_unreachable_leak(validate):
    module = GuppyModule("module")
    module.load_all(quantum)

    @guppy(module)
    def test(b: bool) -> int:
        q = qubit()
        while True:
            if b:
                discard(q)
                return 1
        # This return would leak, but we don't complain since it's unreachable:
        return 0

    validate(module.compile())


def test_unreachable_leak2(validate):
    module = GuppyModule("module")
    module.load_all(quantum)

    @guppy(module)
    def test() -> None:
        if False:
            # This would leak, but we don't complain since it's unreachable:
            q = qubit()

    validate(module.compile())


def test_unreachable_copy(validate):
    module = GuppyModule("module")
    module.load_all(quantum)

    @guppy(module)
    def test() -> None:
        q = qubit()
        discard(q)
        if False:
            # This would be a linearity violation, but we don't complain since it's
            # unreachable:
            h(q)

    validate(module.compile())
