from typing import no_type_check

from guppylang.decorator import guppy
from guppylang.module import GuppyModule
from guppylang.std import angles
from guppylang.std._internal.compiler.quantum import QSYSTEM_EXTENSION
from guppylang.std._internal.util import quantum_op
from guppylang.std.angles import angle
from guppylang.std.quantum import qubit

qsystem = GuppyModule("qsystem")

qsystem.load(qubit)
qsystem.load_all(angles)


@guppy(qsystem)
@no_type_check
def phased_x(q: qubit, angle1: angle, angle2: angle) -> None:
    f1 = float(angle1)
    f2 = float(angle2)
    _phased_x(q, f1, f2)


@guppy(qsystem)
@no_type_check
def zz_phase(q1: qubit, q2: qubit, angle: angle) -> None:
    f = float(angle)
    _zz_phase(q1, q2, f)


# ------------------------------------------------------
# --------- Internal definitions -----------------------
# ------------------------------------------------------


@guppy.hugr_op(quantum_op("PhasedX", ext=QSYSTEM_EXTENSION), module=qsystem)
@no_type_check
def _phased_x(q: qubit, angle1: float, angle2: float) -> None:
    """PhasedX operation from the qsystem extension.

    See `guppylang.prelude.quantum.phased_x` for a public definition that
    accepts angle parameters.
    """


@guppy.hugr_op(quantum_op("ZZPhase", ext=QSYSTEM_EXTENSION), module=qsystem)
@no_type_check
def _zz_phase(q1: qubit, q2: qubit, angle: float) -> None:
    """ZZPhase operation from the qsystem extension.

    See `guppylang.prelude.quantum.phased_x` for a public definition that
    accepts angle parameters.
    """
