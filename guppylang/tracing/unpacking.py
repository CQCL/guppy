from typing import Any, TypeVar

from hugr import ops
from hugr import tys as ht
from hugr.build.dfg import DfBase

from guppylang.ast_util import AstNode
from guppylang.checker.errors.py_errors import IllegalPyExpressionError
from guppylang.checker.expr_checker import python_value_to_guppy_type
from guppylang.compiler.expr_compiler import python_value_to_hugr
from guppylang.error import GuppyError, InternalGuppyError
from guppylang.std._internal.compiler.array import array_new, unpack_array
from guppylang.std._internal.compiler.prelude import build_unwrap
from guppylang.tracing.object import GuppyDefinition, GuppyObject
from guppylang.tracing.state import get_tracing_globals, get_tracing_state
from guppylang.tys.builtin import (
    array_type,
    get_array_length,
    get_element_type,
    is_array_type,
)
from guppylang.tys.const import ConstValue
from guppylang.tys.ty import NoneType, TupleType

P = TypeVar("P", bound=ops.DfParentOp)


def unpack_guppy_object(obj: GuppyObject, builder: DfBase[P]) -> Any:
    """Tries to turn as much of the structure of a GuppyObject into Python objects.

    For example, Guppy tuples are turned into Python tuples and Guppy arrays are turned
    into Python lists.
    """
    match obj._ty:
        case NoneType():
            return None
        case TupleType(element_types=tys):
            unpack = builder.add_op(ops.UnpackTuple(), obj._use_wire(None))
            return tuple(
                unpack_guppy_object(GuppyObject(ty, wire), builder)
                for ty, wire in zip(tys, unpack.outputs(), strict=False)
            )
        case ty if is_array_type(ty):
            length = get_array_length(ty)
            if isinstance(length, ConstValue):
                if length.value == 0:
                    # Zero-length lists cannot be turned back ito Guppy objects since
                    # there is no way to infer the type. Therefore, we should leave
                    # them as Guppy objects here
                    return obj
                elem_ty = get_element_type(ty)
                opt_elems = unpack_array(builder, obj._use_wire(None))
                err = "Linear array element has already been used"
                elems = [build_unwrap(builder, opt_elem, err) for opt_elem in opt_elems]
                return [
                    unpack_guppy_object(GuppyObject(elem_ty, wire), builder)
                    for wire in elems
                ]
            else:
                # Cannot handle generic sizes
                return obj
        case _:
            return obj


def repack_guppy_object(v: Any, builder: DfBase[P]) -> GuppyObject:
    """Undoes the `unpack_guppy_object` operation."""
    match v:
        case GuppyObject() as obj:
            return obj
        case None:
            return GuppyObject(NoneType(), builder.add_op(ops.MakeTuple()))
        case tuple(vs):
            objs = [repack_guppy_object(v, builder) for v in vs]
            return GuppyObject(
                TupleType([obj._ty for obj in objs]),
                builder.add_op(ops.MakeTuple(), *(obj._use_wire(None) for obj in objs)),
            )
        case list(vs) if len(vs) > 0:
            objs = [repack_guppy_object(v, builder) for v in vs]
            elem_ty = objs[0]._ty
            hugr_elem_ty = ht.Option(elem_ty.to_hugr())
            wires = [
                builder.add_op(ops.Tag(1, hugr_elem_ty), obj._use_wire(None))
                for obj in objs
            ]
            return GuppyObject(
                array_type(elem_ty, len(vs)),
                builder.add_op(array_new(hugr_elem_ty, len(vs)), *wires),
            )
        case _:
            raise InternalGuppyError(
                "Can only repack values that were constructed via "
                "`unpack_guppy_object`"
            )


def update_packed_value(v: Any, obj: "GuppyObject", builder: DfBase[P]) -> None:
    """Given a Python value `v` and a `GuppyObject` `obj` that was constructed from `v`
    using `guppy_object_from_py`, updates the wires of any `GuppyObjects` contained in
    `v` to the new wires specified by `obj`.

    Also resets the used flag on any of those updated wires.
    """
    match v:
        case GuppyObject() as v_obj:
            assert v_obj._ty == obj._ty
            v_obj._wire = obj._use_wire(None)
            if v_obj._ty.linear and v_obj._used:
                state = get_tracing_state()
                state.unused_objs.add(v_obj._id)
            v_obj._used = None
        case None:
            assert isinstance(obj._ty, NoneType)
        case tuple(vs):
            assert isinstance(obj._ty, TupleType)
            wires = builder.add_op(ops.UnpackTuple(), obj._use_wire(None)).outputs()
            for v, ty, wire in zip(vs, obj._ty.element_types, wires, strict=True):
                update_packed_value(v, GuppyObject(ty, wire), builder)
        case list(vs) if len(vs) > 0:
            assert is_array_type(obj._ty)
            elem_ty = get_element_type(obj._ty)
            opt_wires = unpack_array(builder, obj._use_wire(None))
            err = "Linear array element has already been used"
            for v, opt_wire in zip(vs, opt_wires, strict=True):
                (wire,) = build_unwrap(builder, opt_wire, err).outputs()
                update_packed_value(v, GuppyObject(elem_ty, wire), builder)
        case _:
            pass


def guppy_object_from_py(v: Any, builder: DfBase[P], node: AstNode) -> GuppyObject:
    match v:
        case GuppyObject() as obj:
            return obj
        case GuppyDefinition() as defn:
            return defn.to_guppy_object()
        case None:
            return GuppyObject(NoneType(), builder.add_op(ops.MakeTuple()))
        case tuple(vs):
            objs = [guppy_object_from_py(v, builder, node) for v in vs]
            return GuppyObject(
                TupleType([obj._ty for obj in objs]),
                builder.add_op(ops.MakeTuple(), *(obj._use_wire(None) for obj in objs)),
            )
        case list(vs) if len(vs) > 0:
            objs = [guppy_object_from_py(v, builder, node) for v in vs]
            elem_ty = objs[0]._ty
            hugr_elem_ty = ht.Option(elem_ty.to_hugr())
            wires = [
                builder.add_op(ops.Tag(1, hugr_elem_ty), obj._use_wire(None))
                for obj in objs
            ]
            return GuppyObject(
                array_type(elem_ty, len(vs)),
                builder.add_op(array_new(hugr_elem_ty, len(vs)), *wires),
            )
        case v:
            ty = python_value_to_guppy_type(v, node, get_tracing_globals())
            if ty is None:
                raise GuppyError(IllegalPyExpressionError(node, type(v)))
            hugr_val = python_value_to_hugr(v, ty)
            assert hugr_val is not None
            return GuppyObject(ty, builder.load(hugr_val))
