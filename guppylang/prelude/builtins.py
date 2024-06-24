"""Guppy module for builtin types and operations."""

# mypy: disable-error-code="empty-body, misc, override, valid-type, no-untyped-def"

from typing import Any

from hugr.serialization import tys

from guppylang.decorator import guppy
from guppylang.definition.custom import DefaultCallChecker, NoopCompiler
from guppylang.error import GuppyError
from guppylang.hugr_builder.hugr import DummyOp
from guppylang.module import GuppyModule
from guppylang.prelude._internal import (
    BoolArithChecker,
    CallableChecker,
    CoercingChecker,
    DunderChecker,
    FailingChecker,
    FloatBoolCompiler,
    FloatDivmodCompiler,
    FloatFloordivCompiler,
    FloatModCompiler,
    IntTruedivCompiler,
    ReversingChecker,
    UnsupportedChecker,
    float_op,
    int_op,
    logic_op,
)
from guppylang.tys.builtin import (
    bool_type_def,
    float_type_def,
    int_type_def,
    linst_type_def,
    list_type_def,
)

builtins = GuppyModule("builtins", import_builtins=False)

T = guppy.type_var(builtins, "T")
L = guppy.type_var(builtins, "L", linear=True)


def py(*_args: Any) -> Any:
    """Function to tag compile-time evaluated Python expressions in a Guppy context.

    This function throws an error when execute in a Python context. It is only intended
    to be used inside Guppy functions.
    """
    raise GuppyError("`py` can only by used in a Guppy context")


@guppy.extend_type(builtins, bool_type_def)
class Bool:
    @guppy.custom(builtins, NoopCompiler())
    def __abs__(self: int) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __add__(self: bool, other: bool) -> int: ...

    @guppy.hugr_op(builtins, logic_op("And", [tys.TypeArg(tys.BoundedNatArg(n=2))]))
    def __and__(self: bool, other: bool) -> bool: ...

    @guppy.custom(builtins, NoopCompiler())
    def __bool__(self: bool) -> bool: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __ceil__(self: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __divmod__(self: bool, other: bool) -> tuple[int, int]: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __eq__(self: bool, other: bool) -> bool: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __float__(self: bool) -> float: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __floor__(self: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __floordiv__(self: bool, other: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __ge__(self: bool, other: bool) -> bool: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __gt__(self: bool, other: bool) -> bool: ...

    @guppy.hugr_op(builtins, DummyOp("ifrombool"))  # TODO: Widen to INT_WIDTH
    def __int__(self: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __invert__(self: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __le__(self: bool, other: bool) -> bool: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __lshift__(self: bool, other: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __lt__(self: bool, other: bool) -> bool: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __mod__(self: bool, other: bool) -> bool: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __mul__(self: bool, other: bool) -> bool: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __ne__(self: bool, other: bool) -> bool: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __neg__(self: bool) -> int: ...

    @guppy.custom(builtins, checker=DunderChecker("__bool__"), higher_order_value=False)
    def __new__(x): ...

    @guppy.hugr_op(builtins, logic_op("Or", [tys.TypeArg(tys.BoundedNatArg(n=2))]))
    def __or__(self: bool, other: bool) -> bool: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __pos__(self: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __pow__(self: bool, other: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __radd__(self: bool, other: bool) -> int: ...

    @guppy.hugr_op(
        builtins,
        logic_op("And", [tys.TypeArg(tys.BoundedNatArg(n=2))]),
        ReversingChecker(),
    )
    def __rand__(self: bool, other: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __rdivmod__(self: bool, other: bool) -> tuple[int, int]: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __rfloordiv__(self: bool, other: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __rlshift__(self: bool, other: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __rmod__(self: bool, other: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __rmul__(self: bool, other: bool) -> int: ...

    @guppy.hugr_op(
        builtins,
        logic_op("Or", [tys.TypeArg(tys.BoundedNatArg(n=2))]),
        ReversingChecker(),
    )
    def __ror__(self: bool, other: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __round__(self: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __rpow__(self: bool, other: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __rrshift__(self: bool, other: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __rshift__(self: bool, other: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __rsub__(self: bool, other: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __rtruediv__(self: bool, other: bool) -> float: ...

    @guppy.hugr_op(builtins, DummyOp("Xor"), ReversingChecker())  # TODO
    def __rxor__(self: bool, other: bool) -> bool: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __sub__(self: bool, other: bool) -> int: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __truediv__(self: bool, other: bool) -> float: ...

    @guppy.custom(builtins, checker=BoolArithChecker())
    def __trunc__(self: bool) -> int: ...

    @guppy.hugr_op(builtins, DummyOp("Xor"))  # TODO
    def __xor__(self: bool, other: bool) -> bool: ...


@guppy.extend_type(builtins, int_type_def)
class Int:
    @guppy.hugr_op(builtins, int_op("iabs"))  # TODO: Maybe wrong? (signed vs unsigned!)
    def __abs__(self: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("iadd"))
    def __add__(self: int, other: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("iand"))
    def __and__(self: int, other: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("itobool"))
    def __bool__(self: int) -> bool: ...

    @guppy.custom(builtins, NoopCompiler())
    def __ceil__(self: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("idivmod_s", num_params=2))
    def __divmod__(self: int, other: int) -> tuple[int, int]: ...

    @guppy.hugr_op(builtins, int_op("ieq"))
    def __eq__(self: int, other: int) -> bool: ...

    @guppy.hugr_op(builtins, int_op("convert_s", "arithmetic.conversions"))
    def __float__(self: int) -> float: ...

    @guppy.custom(builtins, NoopCompiler())
    def __floor__(self: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("idiv_s", num_params=2))
    def __floordiv__(self: int, other: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("ige_s"))
    def __ge__(self: int, other: int) -> bool: ...

    @guppy.hugr_op(builtins, int_op("igt_s"))
    def __gt__(self: int, other: int) -> bool: ...

    @guppy.custom(builtins, NoopCompiler())
    def __int__(self: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("inot"))
    def __invert__(self: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("ile_s"))
    def __le__(self: int, other: int) -> bool: ...

    @guppy.hugr_op(builtins, int_op("ishl", num_params=2))  # TODO: RHS is unsigned
    def __lshift__(self: int, other: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("ilt_s"))
    def __lt__(self: int, other: int) -> bool: ...

    @guppy.hugr_op(builtins, int_op("imod_s", num_params=2))
    def __mod__(self: int, other: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("imul"))
    def __mul__(self: int, other: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("ine"))
    def __ne__(self: int, other: int) -> bool: ...

    @guppy.hugr_op(builtins, int_op("ineg"))
    def __neg__(self: int) -> int: ...

    @guppy.custom(builtins, checker=DunderChecker("__int__"), higher_order_value=False)
    def __new__(x): ...

    @guppy.hugr_op(builtins, int_op("ior"))
    def __or__(self: int, other: int) -> int: ...

    @guppy.custom(builtins, NoopCompiler())
    def __pos__(self: int) -> int: ...

    @guppy.hugr_op(builtins, DummyOp("ipow"))  # TODO
    def __pow__(self: int, other: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("iadd"), ReversingChecker())
    def __radd__(self: int, other: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("rand"), ReversingChecker())
    def __rand__(self: int, other: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("idivmod_s", num_params=2), ReversingChecker())
    def __rdivmod__(self: int, other: int) -> tuple[int, int]: ...

    @guppy.hugr_op(builtins, int_op("idiv_s", num_params=2), ReversingChecker())
    def __rfloordiv__(self: int, other: int) -> int: ...

    @guppy.hugr_op(
        builtins, int_op("ishl", num_params=2), ReversingChecker()
    )  # TODO: RHS is unsigned
    def __rlshift__(self: int, other: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("imod_s", num_params=2), ReversingChecker())
    def __rmod__(self: int, other: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("imul"), ReversingChecker())
    def __rmul__(self: int, other: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("ior"), ReversingChecker())
    def __ror__(self: int, other: int) -> int: ...

    @guppy.custom(builtins, NoopCompiler())
    def __round__(self: int) -> int: ...

    @guppy.hugr_op(builtins, DummyOp("ipow"), ReversingChecker())  # TODO
    def __rpow__(self: int, other: int) -> int: ...

    @guppy.hugr_op(
        builtins, int_op("ishr", num_params=2), ReversingChecker()
    )  # TODO: RHS is unsigned
    def __rrshift__(self: int, other: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("ishr", num_params=2))  # TODO: RHS is unsigned
    def __rshift__(self: int, other: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("isub"), ReversingChecker())
    def __rsub__(self: int, other: int) -> int: ...

    @guppy.custom(builtins, IntTruedivCompiler(), ReversingChecker())
    def __rtruediv__(self: int, other: int) -> float: ...

    @guppy.hugr_op(builtins, int_op("ixor"), ReversingChecker())
    def __rxor__(self: int, other: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("isub"))
    def __sub__(self: int, other: int) -> int: ...

    @guppy.custom(builtins, IntTruedivCompiler())
    def __truediv__(self: int, other: int) -> float: ...

    @guppy.custom(builtins, NoopCompiler())
    def __trunc__(self: int) -> int: ...

    @guppy.hugr_op(builtins, int_op("ixor"))
    def __xor__(self: int, other: int) -> int: ...


@guppy.extend_type(builtins, float_type_def)
class Float:
    @guppy.hugr_op(builtins, float_op("fabs"), CoercingChecker())
    def __abs__(self: float) -> float: ...

    @guppy.hugr_op(builtins, float_op("fadd"), CoercingChecker())
    def __add__(self: float, other: float) -> float: ...

    @guppy.custom(builtins, FloatBoolCompiler(), CoercingChecker())
    def __bool__(self: float) -> bool: ...

    @guppy.hugr_op(builtins, float_op("fceil"), CoercingChecker())
    def __ceil__(self: float) -> float: ...

    @guppy.custom(builtins, FloatDivmodCompiler(), CoercingChecker())
    def __divmod__(self: float, other: float) -> tuple[float, float]: ...

    @guppy.hugr_op(builtins, float_op("feq"), CoercingChecker())
    def __eq__(self: float, other: float) -> bool: ...

    @guppy.custom(builtins, NoopCompiler(), CoercingChecker())
    def __float__(self: float) -> float: ...

    @guppy.hugr_op(builtins, float_op("ffloor"), CoercingChecker())
    def __floor__(self: float) -> float: ...

    @guppy.custom(builtins, FloatFloordivCompiler(), CoercingChecker())
    def __floordiv__(self: float, other: float) -> float: ...

    @guppy.hugr_op(builtins, float_op("fge"), CoercingChecker())
    def __ge__(self: float, other: float) -> bool: ...

    @guppy.hugr_op(builtins, float_op("fgt"), CoercingChecker())
    def __gt__(self: float, other: float) -> bool: ...

    @guppy.hugr_op(
        builtins, float_op("trunc_s", "arithmetic.conversions"), CoercingChecker()
    )
    def __int__(self: float) -> int: ...

    @guppy.hugr_op(builtins, float_op("fle"), CoercingChecker())
    def __le__(self: float, other: float) -> bool: ...

    @guppy.hugr_op(builtins, float_op("flt"), CoercingChecker())
    def __lt__(self: float, other: float) -> bool: ...

    @guppy.custom(builtins, FloatModCompiler(), CoercingChecker())
    def __mod__(self: float, other: float) -> float: ...

    @guppy.hugr_op(builtins, float_op("fmul"), CoercingChecker())
    def __mul__(self: float, other: float) -> float: ...

    @guppy.hugr_op(builtins, float_op("fne"), CoercingChecker())
    def __ne__(self: float, other: float) -> bool: ...

    @guppy.hugr_op(builtins, float_op("fneg"), CoercingChecker())
    def __neg__(self: float, other: float) -> float: ...

    @guppy.custom(
        builtins, checker=DunderChecker("__float__"), higher_order_value=False
    )
    def __new__(x): ...

    @guppy.custom(builtins, NoopCompiler(), CoercingChecker())
    def __pos__(self: float) -> float: ...

    @guppy.hugr_op(builtins, DummyOp("fpow"))  # TODO
    def __pow__(self: float, other: float) -> float: ...

    @guppy.hugr_op(builtins, float_op("fadd"), ReversingChecker(CoercingChecker()))
    def __radd__(self: float, other: float) -> float: ...

    @guppy.custom(builtins, FloatDivmodCompiler(), ReversingChecker(CoercingChecker()))
    def __rdivmod__(self: float, other: float) -> tuple[float, float]: ...

    @guppy.custom(
        builtins, FloatFloordivCompiler(), ReversingChecker(CoercingChecker())
    )
    def __rfloordiv__(self: float, other: float) -> float: ...

    @guppy.custom(builtins, FloatModCompiler(), ReversingChecker(CoercingChecker()))
    def __rmod__(self: float, other: float) -> float: ...

    @guppy.hugr_op(builtins, float_op("fmul"), ReversingChecker(CoercingChecker()))
    def __rmul__(self: float, other: float) -> float: ...

    @guppy.hugr_op(builtins, DummyOp("fround"))  # TODO
    def __round__(self: float) -> float: ...

    @guppy.hugr_op(
        builtins, DummyOp("fpow"), ReversingChecker(DefaultCallChecker())
    )  # TODO
    def __rpow__(self: float, other: float) -> float: ...

    @guppy.hugr_op(builtins, float_op("fsub"), ReversingChecker(CoercingChecker()))
    def __rsub__(self: float, other: float) -> float: ...

    @guppy.hugr_op(builtins, float_op("fdiv"), ReversingChecker(CoercingChecker()))
    def __rtruediv__(self: float, other: float) -> float: ...

    @guppy.hugr_op(builtins, float_op("fsub"), CoercingChecker())
    def __sub__(self: float, other: float) -> float: ...

    @guppy.hugr_op(builtins, float_op("fdiv"), CoercingChecker())
    def __truediv__(self: float, other: float) -> float: ...

    @guppy.hugr_op(
        builtins, float_op("trunc_s", "arithmetic.conversions"), CoercingChecker()
    )
    def __trunc__(self: float) -> float: ...


@guppy.extend_type(builtins, list_type_def)
class List:
    @guppy.hugr_op(builtins, DummyOp("Concat"))
    def __add__(self: list[T], other: list[T]) -> list[T]: ...

    @guppy.hugr_op(builtins, DummyOp("IsEmpty"))
    def __bool__(self: list[T]) -> bool: ...

    @guppy.hugr_op(builtins, DummyOp("Contains"))
    def __contains__(self: list[T], el: T) -> bool: ...

    @guppy.hugr_op(builtins, DummyOp("AssertEmpty"))
    def __end__(self: list[T]) -> None: ...

    @guppy.hugr_op(builtins, DummyOp("Lookup"))
    def __getitem__(self: list[T], idx: int) -> T: ...

    @guppy.hugr_op(builtins, DummyOp("IsNonEmpty"))
    def __hasnext__(self: list[T]) -> tuple[bool, list[T]]: ...

    @guppy.custom(builtins, NoopCompiler())
    def __iter__(self: list[T]) -> list[T]: ...

    @guppy.hugr_op(builtins, DummyOp("Length"))
    def __len__(self: list[T]) -> int: ...

    @guppy.hugr_op(builtins, DummyOp("Repeat"))
    def __mul__(self: list[T], other: int) -> list[T]: ...

    @guppy.hugr_op(builtins, DummyOp("Pop"))
    def __next__(self: list[T]) -> tuple[T, list[T]]: ...

    @guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
    def __new__(x): ...

    @guppy.custom(builtins, checker=FailingChecker("Guppy lists are immutable"))
    def __setitem__(self: list[T], idx: int, value: T) -> None: ...

    @guppy.hugr_op(builtins, DummyOp("Append"), ReversingChecker())
    def __radd__(self: list[T], other: list[T]) -> list[T]: ...

    @guppy.hugr_op(builtins, DummyOp("Repeat"), ReversingChecker())
    def __rmul__(self: list[T], other: int) -> list[T]: ...

    @guppy.custom(builtins, checker=FailingChecker("Guppy lists are immutable"))
    def append(self: list[T], elt: T) -> None: ...

    @guppy.custom(builtins, checker=FailingChecker("Guppy lists are immutable"))
    def clear(self: list[T]) -> None: ...

    @guppy.custom(builtins, NoopCompiler())  # Can be noop since lists are immutable
    def copy(self: list[T]) -> list[T]: ...

    @guppy.hugr_op(builtins, DummyOp("Count"))
    def count(self: list[T], elt: T) -> int: ...

    @guppy.custom(builtins, checker=FailingChecker("Guppy lists are immutable"))
    def extend(self: list[T], seq: None) -> None: ...

    @guppy.hugr_op(builtins, DummyOp("Find"))
    def index(self: list[T], elt: T) -> int: ...

    @guppy.custom(builtins, checker=FailingChecker("Guppy lists are immutable"))
    def pop(self: list[T], idx: int) -> None: ...

    @guppy.custom(builtins, checker=FailingChecker("Guppy lists are immutable"))
    def remove(self: list[T], elt: T) -> None: ...

    @guppy.custom(builtins, checker=FailingChecker("Guppy lists are immutable"))
    def reverse(self: list[T]) -> None: ...

    @guppy.custom(builtins, checker=FailingChecker("Guppy lists are immutable"))
    def sort(self: list[T]) -> None: ...


linst = list


@guppy.extend_type(builtins, linst_type_def)
class Linst:
    @guppy.hugr_op(builtins, DummyOp("Append"))
    def __add__(self: linst[L], other: linst[L]) -> linst[L]: ...

    @guppy.hugr_op(builtins, DummyOp("AssertEmpty"))
    def __end__(self: linst[L]) -> None: ...

    @guppy.hugr_op(builtins, DummyOp("IsNonempty"))
    def __hasnext__(self: linst[L]) -> tuple[bool, linst[L]]: ...

    @guppy.custom(builtins, NoopCompiler())
    def __iter__(self: linst[L]) -> linst[L]: ...

    @guppy.hugr_op(builtins, DummyOp("Length"))
    def __len__(self: linst[L]) -> tuple[int, linst[L]]: ...

    @guppy.hugr_op(builtins, DummyOp("Pop"))
    def __next__(self: linst[L]) -> tuple[L, linst[L]]: ...

    @guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
    def __new__(x): ...

    @guppy.hugr_op(builtins, DummyOp("Append"), ReversingChecker())
    def __radd__(self: linst[L], other: linst[L]) -> linst[L]: ...

    @guppy.hugr_op(builtins, DummyOp("Repeat"), ReversingChecker())
    def __rmul__(self: linst[L], other: int) -> linst[L]: ...

    @guppy.hugr_op(builtins, DummyOp("Push"))
    def append(self: linst[L], elt: L) -> linst[L]: ...

    @guppy.hugr_op(builtins, DummyOp("PopAt"))
    def pop(self: linst[L], idx: int) -> tuple[L, linst[L]]: ...

    @guppy.hugr_op(builtins, DummyOp("Reverse"))
    def reverse(self: linst[L]) -> linst[L]: ...

    @guppy.custom(builtins, checker=FailingChecker("Guppy lists are immutable"))
    def sort(self: list[T]) -> None: ...


@guppy.custom(builtins, checker=DunderChecker("__abs__"), higher_order_value=False)
def abs(x): ...


@guppy.custom(builtins, checker=CallableChecker(), higher_order_value=False)
def callable(x): ...


@guppy.custom(
    builtins, checker=DunderChecker("__divmod__", num_args=2), higher_order_value=False
)
def divmod(x, y): ...


@guppy.custom(builtins, checker=DunderChecker("__len__"), higher_order_value=False)
def len(x): ...


@guppy.custom(
    builtins, checker=DunderChecker("__pow__", num_args=2), higher_order_value=False
)
def pow(x, y): ...


@guppy.custom(builtins, checker=DunderChecker("__round__"), higher_order_value=False)
def round(x): ...


# Python builtins that are not supported yet:


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def aiter(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def all(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def anext(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def any(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def bin(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def breakpoint(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def bytearray(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def bytes(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def chr(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def classmethod(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def compile(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def complex(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def delattr(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def dict(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def dir(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def enumerate(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def eval(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def exec(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def filter(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def format(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def forozenset(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def getattr(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def globals(): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def hasattr(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def hash(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def help(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def hex(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def id(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def input(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def isinstance(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def issubclass(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def iter(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def locals(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def map(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def max(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def memoryview(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def min(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def next(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def object(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def oct(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def open(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def ord(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def print(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def property(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def range(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def repr(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def reversed(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def set(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def setattr(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def slice(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def sorted(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def staticmethod(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def str(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def sum(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def super(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def type(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def vars(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def zip(x): ...


@guppy.custom(builtins, checker=UnsupportedChecker(), higher_order_value=False)
def __import__(x): ...
