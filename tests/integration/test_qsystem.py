from hugr.package import ModulePointer

import guppylang.decorator
from guppylang.module import GuppyModule
from guppylang.std.angles import angle

from guppylang.std.builtins import owned
from guppylang.std.quantum import qubit
from guppylang.std.qsystem.functional import (
    phased_x,
    zz_phase,
    qsystem_functional,
    measure_and_reset,
    zz_max,
    rz,
    measure,
    qfree,
)


def compile_qsystem_guppy(fn) -> ModulePointer:
    """A decorator that combines @guppy with HUGR compilation.

    Modified version of `tests.util.compile_guppy` that loads the qsytem module.
    """
    assert not isinstance(
        fn,
        GuppyModule,
    ), "`@compile_qsystem_guppy` does not support extra arguments."

    module = GuppyModule("module")
    module.load(angle, qubit)
    module.load_all(qsystem_functional)
    guppylang.decorator.guppy(module)(fn)
    return module.compile()


def test_qsystem(validate):
    """Compile various operations from the qsystem extension."""

    @compile_qsystem_guppy
    def test(q1: qubit @ owned, q2: qubit @ owned, a1: angle) -> bool:
        q1 = phased_x(q1, a1, a1)
        q1, q2 = zz_phase(q1, q2, a1)
        q1 = rz(q1, a1)
        q1, q2 = zz_max(q1, q2)
        q1, b = measure_and_reset(q1)
        q1 = reset(q1)
        b = measure(q1)
        qfree(q2)
        return b

    validate(test)
