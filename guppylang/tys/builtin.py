from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, TypeGuard

import hugr.std
import hugr.std.collections.array
import hugr.std.collections.list
from hugr import tys as ht

from guppylang.ast_util import AstNode
from guppylang.definition.common import DefId
from guppylang.definition.ty import OpaqueTypeDef, TypeDef
from guppylang.error import GuppyError, InternalGuppyError
from guppylang.experimental import check_lists_enabled
from guppylang.tys.arg import Argument, ConstArg, TypeArg
from guppylang.tys.const import Const, ConstValue
from guppylang.tys.errors import WrongNumberOfTypeArgsError
from guppylang.tys.param import ConstParam, TypeParam
from guppylang.tys.ty import (
    FunctionType,
    NoneType,
    NumericType,
    OpaqueType,
    TupleType,
    Type,
)

if TYPE_CHECKING:
    from guppylang.checker.core import Globals


@dataclass(frozen=True)
class CallableTypeDef(TypeDef):
    """Type definition associated with the builtin `Callable` type.

    Any impls on functions can be registered with this definition.
    """

    name: Literal["Callable"] = field(default="Callable", init=False)

    def check_instantiate(
        self, args: Sequence[Argument], globals: "Globals", loc: AstNode | None = None
    ) -> FunctionType:
        # Callable types are constructed using special logic in the type parser
        raise InternalGuppyError("Tried to `Callable` type via `check_instantiate`")


@dataclass(frozen=True)
class _TupleTypeDef(TypeDef):
    """Type definition associated with the builtin `tuple` type.

    Any impls on tuples can be registered with this definition.
    """

    name: Literal["tuple"] = field(default="tuple", init=False)

    def check_instantiate(
        self, args: Sequence[Argument], globals: "Globals", loc: AstNode | None = None
    ) -> TupleType:
        # We accept any number of arguments. If users just write `tuple`, we give them
        # the empty tuple type. We just have to make sure that the args are of kind type
        args = [
            # TODO: Better error location
            TypeParam(0, f"T{i}", can_be_linear=True).check_arg(arg, loc).ty
            for i, arg in enumerate(args)
        ]
        return TupleType(args)


@dataclass(frozen=True)
class _NoneTypeDef(TypeDef):
    """Type definition associated with the builtin `None` type.

    Any impls on None can be registered with this definition.
    """

    name: Literal["None"] = field(default="None", init=False)

    def check_instantiate(
        self, args: Sequence[Argument], globals: "Globals", loc: AstNode | None = None
    ) -> NoneType:
        if args:
            raise GuppyError(WrongNumberOfTypeArgsError(loc, 0, len(args), "None"))
        return NoneType()


@dataclass(frozen=True)
class _NumericTypeDef(TypeDef):
    """Type definition associated with the builtin numeric types.

    Any impls on numerics can be registered with these definitions.
    """

    ty: NumericType

    def check_instantiate(
        self, args: Sequence[Argument], globals: "Globals", loc: AstNode | None = None
    ) -> NumericType:
        if args:
            raise GuppyError(WrongNumberOfTypeArgsError(loc, 0, len(args), self.name))
        return self.ty


@dataclass(frozen=True)
class _ListTypeDef(OpaqueTypeDef):
    """Type definition associated with the builtin `list` type.

    We have a custom definition to disable usage of lists unless experimental features
    are enabled.
    """

    def check_instantiate(
        self, args: Sequence[Argument], globals: "Globals", loc: AstNode | None = None
    ) -> OpaqueType:
        check_lists_enabled(loc)
        return super().check_instantiate(args, globals, loc)


def _list_to_hugr(args: Sequence[Argument]) -> ht.Type:
    # Type checker ensures that we get a single arg of kind type
    [arg] = args
    assert isinstance(arg, TypeArg)
    # Linear elements are turned into an optional to enable unsafe indexing.
    # See `ListGetitemCompiler` for details.
    elem_ty = ht.Option(arg.ty.to_hugr()) if arg.ty.linear else arg.ty.to_hugr()
    return hugr.std.collections.list.List(elem_ty)


def _array_to_hugr(args: Sequence[Argument]) -> ht.Type:
    # Type checker ensures that we get a two args
    [ty_arg, len_arg] = args
    assert isinstance(ty_arg, TypeArg)
    assert isinstance(len_arg, ConstArg)

    # Linear elements are turned into an optional to enable unsafe indexing.
    # See `ArrayGetitemCompiler` for details.
    # Same also for classical arrays, see https://github.com/CQCL/guppylang/issues/629
    elem_ty = ht.Option(ty_arg.ty.to_hugr())
    hugr_arg = len_arg.to_hugr()

    return hugr.std.collections.array.Array(elem_ty, hugr_arg)


def _sized_iter_to_hugr(args: Sequence[Argument]) -> ht.Type:
    [ty_arg, len_arg] = args
    assert isinstance(ty_arg, TypeArg)
    assert isinstance(len_arg, ConstArg)
    return ty_arg.ty.to_hugr()


callable_type_def = CallableTypeDef(DefId.fresh(), None)
tuple_type_def = _TupleTypeDef(DefId.fresh(), None)
none_type_def = _NoneTypeDef(DefId.fresh(), None)
bool_type_def = OpaqueTypeDef(
    id=DefId.fresh(),
    name="bool",
    defined_at=None,
    params=[],
    always_linear=False,
    to_hugr=lambda _: ht.Bool,
)
nat_type_def = _NumericTypeDef(
    DefId.fresh(), "nat", None, NumericType(NumericType.Kind.Nat)
)
int_type_def = _NumericTypeDef(
    DefId.fresh(), "int", None, NumericType(NumericType.Kind.Int)
)
float_type_def = _NumericTypeDef(
    DefId.fresh(), "float", None, NumericType(NumericType.Kind.Float)
)
string_type_def = OpaqueTypeDef(
    id=DefId.fresh(),
    name="str",
    defined_at=None,
    params=[],
    always_linear=False,
    to_hugr=lambda _: hugr.std.PRELUDE.get_type("string").instantiate([]),
)
list_type_def = _ListTypeDef(
    id=DefId.fresh(),
    name="list",
    defined_at=None,
    params=[TypeParam(0, "T", can_be_linear=True)],
    always_linear=False,
    to_hugr=_list_to_hugr,
)
array_type_def = OpaqueTypeDef(
    id=DefId.fresh(),
    name="array",
    defined_at=None,
    params=[
        TypeParam(0, "T", can_be_linear=True),
        ConstParam(1, "n", NumericType(NumericType.Kind.Nat)),
    ],
    always_linear=False,
    to_hugr=_array_to_hugr,
)
sized_iter_type_def = OpaqueTypeDef(
    id=DefId.fresh(),
    name="SizedIter",
    defined_at=None,
    params=[
        TypeParam(0, "T", can_be_linear=True),
        ConstParam(1, "n", NumericType(NumericType.Kind.Nat)),
    ],
    always_linear=False,
    to_hugr=_sized_iter_to_hugr,
)


def bool_type() -> OpaqueType:
    return OpaqueType([], bool_type_def)


def nat_type() -> NumericType:
    return NumericType(NumericType.Kind.Nat)


def int_type() -> NumericType:
    return NumericType(NumericType.Kind.Int)


def float_type() -> NumericType:
    return NumericType(NumericType.Kind.Float)


def string_type() -> OpaqueType:
    return OpaqueType([], string_type_def)


def list_type(element_ty: Type) -> OpaqueType:
    return OpaqueType([TypeArg(element_ty)], list_type_def)


def array_type(element_ty: Type, length: int | Const) -> OpaqueType:
    if isinstance(length, int):
        length = ConstValue(nat_type(), length)
    return OpaqueType([TypeArg(element_ty), ConstArg(length)], array_type_def)


def sized_iter_type(iter_type: Type, size: int | Const) -> OpaqueType:
    if isinstance(size, int):
        size = ConstValue(nat_type(), size)
    return OpaqueType([TypeArg(iter_type), ConstArg(size)], sized_iter_type_def)


def is_bool_type(ty: Type) -> bool:
    return isinstance(ty, OpaqueType) and ty.defn == bool_type_def


def is_string_type(ty: Type) -> bool:
    return isinstance(ty, OpaqueType) and ty.defn == string_type_def


def is_list_type(ty: Type) -> bool:
    return isinstance(ty, OpaqueType) and ty.defn == list_type_def


def is_array_type(ty: Type) -> TypeGuard[OpaqueType]:
    return isinstance(ty, OpaqueType) and ty.defn == array_type_def


def is_sized_iter_type(ty: Type) -> TypeGuard[OpaqueType]:
    return isinstance(ty, OpaqueType) and ty.defn == sized_iter_type_def


def get_element_type(ty: Type) -> Type:
    assert isinstance(ty, OpaqueType)
    assert ty.defn == list_type_def or ty.defn == array_type_def
    (arg, *_) = ty.args
    assert isinstance(arg, TypeArg)
    return arg.ty


def get_array_length(ty: Type) -> Const:
    assert isinstance(ty, OpaqueType)
    assert ty.defn == array_type_def
    [_, length_arg] = ty.args
    assert isinstance(length_arg, ConstArg)
    return length_arg.const


def get_iter_size(ty: Type) -> Const:
    assert isinstance(ty, OpaqueType)
    assert ty.defn == sized_iter_type_def
    match ty.args:
        case [_, ConstArg(const)]:
            return const
        case _:
            raise InternalGuppyError("Unexpected type args")
