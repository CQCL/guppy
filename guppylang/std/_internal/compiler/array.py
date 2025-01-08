"""Compilers building array functions on top of hugr standard operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from hugr import Wire, ops
from hugr import tys as ht
from hugr.std.collections.array import EXTENSION

from guppylang.definition.custom import CustomCallCompiler
from guppylang.definition.value import CallReturnWires
from guppylang.error import InternalGuppyError
from guppylang.std._internal.compiler.arithmetic import convert_itousize
from guppylang.std._internal.compiler.prelude import (
    build_expect_none,
    build_unwrap,
    build_unwrap_left,
    build_unwrap_right,
)
from guppylang.tys.arg import ConstArg, TypeArg

if TYPE_CHECKING:
    from hugr.build.dfg import DfBase


# ------------------------------------------------------
# --------------- std.array operations -----------------
# ------------------------------------------------------


def _instantiate_array_op(
    name: str,
    elem_ty: ht.Type,
    length: ht.TypeArg,
    inp: list[ht.Type],
    out: list[ht.Type],
) -> ops.ExtOp:
    return EXTENSION.get_op(name).instantiate(
        [length, ht.TypeTypeArg(elem_ty)], ht.FunctionType(inp, out)
    )


def array_type(elem_ty: ht.Type, length: ht.TypeArg) -> ht.ExtType:
    """Returns the hugr type of a fixed length array."""
    elem_arg = ht.TypeTypeArg(elem_ty)
    return EXTENSION.types["array"].instantiate([length, elem_arg])


def array_new(elem_ty: ht.Type, length: int) -> ops.ExtOp:
    """Returns an operation that creates a new fixed length array."""
    length_arg = ht.BoundedNatArg(length)
    arr_ty = array_type(elem_ty, length_arg)
    return _instantiate_array_op(
        "new_array", elem_ty, length_arg, [elem_ty] * length, [arr_ty]
    )


def array_get(elem_ty: ht.Type, length: ht.TypeArg) -> ops.ExtOp:
    """Returns an array `get` operation."""
    assert elem_ty.type_bound() == ht.TypeBound.Copyable
    arr_ty = array_type(elem_ty, length)
    return _instantiate_array_op(
        "get", elem_ty, length, [arr_ty, ht.USize()], [ht.Option(elem_ty)]
    )


def array_set(elem_ty: ht.Type, length: ht.TypeArg) -> ops.ExtOp:
    """Returns an array `set` operation."""
    arr_ty = array_type(elem_ty, length)
    return _instantiate_array_op(
        "set",
        elem_ty,
        length,
        [arr_ty, ht.USize(), elem_ty],
        [ht.Either([elem_ty, arr_ty], [elem_ty, arr_ty])],
    )


def array_pop(elem_ty: ht.Type, length: int, from_left: bool) -> ops.ExtOp:
    """Returns an operation that pops an element from the left of an array."""
    assert length > 0
    length_arg = ht.BoundedNatArg(length)
    arr_ty = array_type(elem_ty, length_arg)
    popped_arr_ty = array_type(elem_ty, ht.BoundedNatArg(length - 1))
    op = "pop_left" if from_left else "pop_right"
    return _instantiate_array_op(
        op, elem_ty, length_arg, [arr_ty], [ht.Option(elem_ty, popped_arr_ty)]
    )


def array_discard_empty(elem_ty: ht.Type) -> ops.ExtOp:
    """Returns an operation that discards an array of length zero."""
    arr_ty = array_type(elem_ty, ht.BoundedNatArg(0))
    return EXTENSION.get_op("discard_empty").instantiate(
        [ht.TypeTypeArg(elem_ty)], ht.FunctionType([arr_ty], [])
    )


def array_scan(
    elem_ty: ht.Type,
    length: ht.TypeArg,
    new_elem_ty: ht.Type,
    accumulators: list[ht.Type],
) -> ops.ExtOp:
    """Returns an operation that maps and folds a function across an array."""
    ty_args = [
        length,
        ht.TypeTypeArg(elem_ty),
        ht.TypeTypeArg(new_elem_ty),
        ht.SequenceArg([ht.TypeTypeArg(acc) for acc in accumulators]),
        ht.ExtensionsArg([]),
    ]
    ins = [
        array_type(elem_ty, length),
        ht.FunctionType([elem_ty, *accumulators], [new_elem_ty, *accumulators]),
        *accumulators,
    ]
    outs = [array_type(new_elem_ty, length), *accumulators]
    return EXTENSION.get_op("scan").instantiate(ty_args, ht.FunctionType(ins, outs))


def array_map(elem_ty: ht.Type, length: ht.TypeArg, new_elem_ty: ht.Type) -> ops.ExtOp:
    """Returns an operation that maps a function across an array."""
    return array_scan(elem_ty, length, new_elem_ty, accumulators=[])


def array_repeat(elem_ty: ht.Type, length: ht.TypeArg) -> ops.ExtOp:
    """Returns an array `repeat` operation."""
    return EXTENSION.get_op("repeat").instantiate(
        [length, ht.TypeTypeArg(elem_ty), ht.ExtensionsArg([])],
        ht.FunctionType(
            [ht.FunctionType([], [elem_ty])], [array_type(elem_ty, length)]
        ),
    )


# ------------------------------------------------------
# --------- Custom compilers for non-native ops --------
# ------------------------------------------------------


P = TypeVar("P", bound=ops.DfParentOp)


def unpack_array(builder: DfBase[P], array: Wire) -> list[Wire]:
    """ """
    # TODO: This should be an op
    array_ty = builder.hugr.port_type(array.out_port())
    assert isinstance(array_ty, ht.ExtType)
    err = "Internal error: array unpacking failed"
    match array_ty.args:
        case [ht.BoundedNatArg(length), ht.TypeTypeArg(elem_ty)]:
            elems: list[Wire] = []
            for i in range(length):
                res = builder.add_op(
                    array_pop(elem_ty, length - i, from_left=True), array
                )
                elem, array = build_unwrap(builder, res, err)
                elems.append(elem)
            builder.add_op(array_discard_empty(elem_ty), array)
            return elems
        case _:
            raise InternalGuppyError("Invalid array type args")


class ArrayCompiler(CustomCallCompiler):
    """Base class for custom array op compilers."""

    @property
    def elem_ty(self) -> ht.Type:
        """The element type for the array op that is being compiled."""
        match self.type_args:
            case [TypeArg(ty=elem_ty), _]:
                return elem_ty.to_hugr()
            case _:
                raise InternalGuppyError("Invalid array type args")

    @property
    def length(self) -> ht.TypeArg:
        """The length for the array op that is being compiled."""
        match self.type_args:
            case [_, ConstArg(const)]:  # Const includes both literals and variables
                return const.to_arg().to_hugr()
            case _:
                raise InternalGuppyError("Invalid array type args")


class NewArrayCompiler(ArrayCompiler):
    """Compiler for the `array.__new__` function."""

    def build_classical_array(self, elems: list[Wire]) -> Wire:
        """Lowers a call to `array.__new__` for classical arrays."""
        # See https://github.com/CQCL/guppylang/issues/629
        return self.build_linear_array(elems)

    def build_linear_array(self, elems: list[Wire]) -> Wire:
        """Lowers a call to `array.__new__` for linear arrays."""
        elem_opts = [
            self.builder.add_op(ops.Some(self.elem_ty), elem) for elem in elems
        ]
        return self.builder.add_op(
            array_new(ht.Option(self.elem_ty), len(elems)), *elem_opts
        )

    def compile(self, args: list[Wire]) -> list[Wire]:
        if self.elem_ty.type_bound() == ht.TypeBound.Any:
            return [self.build_linear_array(args)]
        else:
            return [self.build_classical_array(args)]


class ArrayGetitemCompiler(ArrayCompiler):
    """Compiler for the `array.__getitem__` function."""

    def build_classical_getitem(self, array: Wire, idx: Wire) -> CallReturnWires:
        """Lowers a call to `array.__getitem__` for classical arrays."""
        # See https://github.com/CQCL/guppylang/issues/629
        elem_opt_ty = ht.Option(self.elem_ty)
        idx = self.builder.add_op(convert_itousize(), idx)
        result = self.builder.add_op(array_get(elem_opt_ty, self.length), array, idx)
        elem_opt = build_unwrap(self.builder, result, "Array index out of bounds")
        elem = build_unwrap(self.builder, elem_opt, "array.__getitem__: Internal error")
        return CallReturnWires(regular_returns=[elem], inout_returns=[array])

    def build_linear_getitem(self, array: Wire, idx: Wire) -> CallReturnWires:
        """Lowers a call to `array.__getitem__` for linear arrays."""
        # Swap out the element at the given index with `None`. The `to_hugr`
        # implementation of the array type ensures that linear element types are turned
        # into optionals.
        elem_opt_ty = ht.Option(self.elem_ty)
        none = self.builder.add_op(ops.Tag(0, elem_opt_ty))
        idx = self.builder.add_op(convert_itousize(), idx)
        result = self.builder.add_op(
            array_set(elem_opt_ty, self.length), array, idx, none
        )
        elem_opt, array = build_unwrap_right(
            self.builder, result, "Array index out of bounds"
        )
        elem = build_unwrap(
            self.builder, elem_opt, "Linear array element has already been used"
        )
        return CallReturnWires(regular_returns=[elem], inout_returns=[array])

    def compile_with_inouts(self, args: list[Wire]) -> CallReturnWires:
        [array, idx] = args
        if self.elem_ty.type_bound() == ht.TypeBound.Any:
            return self.build_linear_getitem(array, idx)
        else:
            return self.build_classical_getitem(array, idx)

    def compile(self, args: list[Wire]) -> list[Wire]:
        raise InternalGuppyError("Call compile_with_inouts instead")


class ArraySetitemCompiler(ArrayCompiler):
    """Compiler for the `array.__setitem__` function."""

    def build_classical_setitem(
        self, array: Wire, idx: Wire, elem: Wire
    ) -> CallReturnWires:
        """Lowers a call to `array.__setitem__` for classical arrays."""
        # See https://github.com/CQCL/guppylang/issues/629
        elem_opt_ty = ht.Option(self.elem_ty)
        idx = self.builder.add_op(convert_itousize(), idx)
        elem_opt = self.builder.add_op(ops.Some(self.elem_ty), elem)
        result = self.builder.add_op(
            array_set(elem_opt_ty, self.length), array, idx, elem_opt
        )
        # Unwrap the result, but we don't have to hold onto the returned old value
        _, array = build_unwrap_right(self.builder, result, "Array index out of bounds")
        return CallReturnWires(regular_returns=[], inout_returns=[array])

    def build_linear_setitem(
        self, array: Wire, idx: Wire, elem: Wire
    ) -> CallReturnWires:
        """Lowers a call to `array.__setitem__` for linear arrays."""
        # Embed the element into an optional
        elem_opt_ty = ht.Option(self.elem_ty)
        elem = self.builder.add_op(ops.Some(self.elem_ty), elem)
        idx = self.builder.add_op(convert_itousize(), idx)
        result = self.builder.add_op(
            array_set(elem_opt_ty, self.length), array, idx, elem
        )
        old_elem_opt, array = build_unwrap_right(
            self.builder, result, "Array index out of bounds"
        )
        # Check that the old element was `None`
        build_unwrap_left(
            self.builder, old_elem_opt, "Linear array element has not been used"
        )
        return CallReturnWires(regular_returns=[], inout_returns=[array])

    def compile_with_inouts(self, args: list[Wire]) -> CallReturnWires:
        [array, idx, elem] = args
        if self.elem_ty.type_bound() == ht.TypeBound.Any:
            return self.build_linear_setitem(array, idx, elem)
        else:
            return self.build_classical_setitem(array, idx, elem)

    def compile(self, args: list[Wire]) -> list[Wire]:
        raise InternalGuppyError("Call compile_with_inouts instead")


class ArrayIterEndCompiler(ArrayCompiler):
    """Compiler for the `ArrayIter.__end__` method."""

    def compile(self, args: list[Wire]) -> list[Wire]:
        # For linear array iterators, map the array of optional elements to an
        # `array[None, n]` that we can discard.
        if self.elem_ty.type_bound() == ht.TypeBound.Any:
            elem_opt_ty = ht.Option(self.elem_ty)
            none_ty = ht.UnitSum(1)
            # Define `unwrap_none` function. If any of the elements are not `None`,
            # then the users must have called `__end__` prematurely and we panic.
            func = self.builder.define_function("unwrap_none", [elem_opt_ty], [none_ty])
            err_msg = "Linear array element has not been used in iterator"
            build_expect_none(func, func.inputs()[0], err_msg)
            func.set_outputs(func.add_op(ops.Tag(0, none_ty)))
            func = self.builder.load_function(func)
            # Map it over the array so that the resulting array is no longer linear and
            # can be discarded
            [array_iter] = args
            array, _ = self.builder.add_op(ops.UnpackTuple(), array_iter)
            self.builder.add_op(
                array_map(elem_opt_ty, self.length, none_ty), array, func
            )
        return []
