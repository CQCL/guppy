from guppylang.decorator import guppy
from guppylang.prelude.builtins import nat, range
from guppylang.module import GuppyModule
from tests.util import compile_guppy


def test_stop_only(validate, run_int_fn):
    module = GuppyModule("test_range1")

    @guppy(module)
    def main() -> int:
        total = 0
        for x in range(5):
            total += x + 100 # Make the initial 0 obvious
        return total

    @guppy(module)
    def negative() -> int:
        total = 0
        for x in range(-3):
            total += 100 + x
        return total

    compiled = module.compile()
    validate(compiled)
    run_int_fn(compiled, expected=510)
    run_int_fn(compiled, expected=0, fn_name="negative")

def test_start_stop(validate, run_int_fn):
    module = GuppyModule("test_range2")

    @guppy(module)
    def simple() -> int:
        total = 0
        for x in range(3, 5):
            total += x
        return total

    @guppy(module)
    def empty() -> int:
        total = 0
        for x in range(5, 3):
            total += x + 100
        return total

    compiled=module.compile()
    validate(compiled)
    run_int_fn(compiled, expected=7, fn_name="simple")
    run_int_fn(compiled, expected=0, fn_name="empty")

def test_with_step(validate, run_int_fn):
    module =GuppyModule("test_range3")

    @guppy(module)
    def evens() -> int:
        total = 0
        for x in range(2, 7, 2):
            total += x
        return total

    @guppy(module)
    def negative_step() -> int:
        total = 0
        for x in range(5, 3, -1):
            total += x
        return total

    @guppy(module)
    def empty() -> int:
        total = 0
        for x in range(3, 5, -1):
            total += 100 + x
        return total

    compiled = module.compile()
    validate(compiled)
    run_int_fn(compiled, expected=12, fn_name="evens")
    run_int_fn(compiled, expected=9, fn_name="negative_step")
    run_int_fn(compiled, expected=0, fn_name="empty")
