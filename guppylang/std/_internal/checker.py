import ast
from dataclasses import dataclass
from typing import ClassVar, cast

from guppylang.ast_util import AstNode, with_loc, with_type
from guppylang.checker.core import Context
from guppylang.checker.errors.generic import ExpectedError, UnsupportedError
from guppylang.checker.errors.type_errors import TypeMismatchError
from guppylang.checker.expr_checker import (
    ExprChecker,
    ExprSynthesizer,
    check_call,
    check_num_args,
    check_type_against,
    synthesize_call,
)
from guppylang.definition.custom import (
    CustomCallChecker,
    CustomFunctionDef,
    DefaultCallChecker,
)
from guppylang.definition.struct import CheckedStructDef, RawStructDef
from guppylang.diagnostic import Error, Note
from guppylang.error import GuppyError, GuppyTypeError, InternalGuppyError
from guppylang.nodes import GlobalCall, ResultExpr
from guppylang.tys.arg import ConstArg, TypeArg
from guppylang.tys.builtin import (
    array_type,
    array_type_def,
    bool_type,
    int_type,
    is_array_type,
    is_bool_type,
    sized_iter_type,
)
from guppylang.tys.const import Const, ConstValue
from guppylang.tys.subst import Inst, Subst
from guppylang.tys.ty import (
    FunctionType,
    NoneType,
    NumericType,
    StructType,
    Type,
)


class CoercingChecker(DefaultCallChecker):
    """Function call type checker that automatically coerces arguments to float."""

    def synthesize(self, args: list[ast.expr]) -> tuple[ast.expr, Type]:
        for i in range(len(args)):
            args[i], ty = ExprSynthesizer(self.ctx).synthesize(args[i])
            if isinstance(ty, NumericType) and ty.kind != NumericType.Kind.Float:
                to_float = self.ctx.globals.get_instance_func(ty, "__float__")
                assert to_float is not None
                args[i], _ = to_float.synthesize_call([args[i]], self.node, self.ctx)
        return super().synthesize(args)


class ReversingChecker(CustomCallChecker):
    """Call checker that reverses the arguments after checking."""

    base_checker: CustomCallChecker

    def __init__(self, base_checker: CustomCallChecker | None = None):
        self.base_checker = base_checker or DefaultCallChecker()

    def _setup(self, ctx: Context, node: AstNode, func: CustomFunctionDef) -> None:
        super()._setup(ctx, node, func)
        self.base_checker._setup(ctx, node, func)

    def check(self, args: list[ast.expr], ty: Type) -> tuple[ast.expr, Subst]:
        expr, subst = self.base_checker.check(args, ty)
        if isinstance(expr, GlobalCall):
            expr.args = list(reversed(expr.args))
        return expr, subst

    def synthesize(self, args: list[ast.expr]) -> tuple[ast.expr, Type]:
        expr, ty = self.base_checker.synthesize(args)
        if isinstance(expr, GlobalCall):
            expr.args = list(reversed(expr.args))
        return expr, ty


class UnsupportedChecker(CustomCallChecker):
    """Call checker for Python builtin functions that are not available in Guppy.

    Gives the uses a nicer error message when they try to use an unsupported feature.
    """

    def synthesize(self, args: list[ast.expr]) -> tuple[ast.expr, Type]:
        err = UnsupportedError(
            self.node, f"Builtin method `{self.func.name}`", singular=True
        )
        raise GuppyError(err)

    def check(self, args: list[ast.expr], ty: Type) -> tuple[ast.expr, Subst]:
        err = UnsupportedError(
            self.node, f"Builtin method `{self.func.name}`", singular=True
        )
        raise GuppyError(err)


class DunderChecker(CustomCallChecker):
    """Call checker for builtin functions that call out to dunder instance methods"""

    dunder_name: str
    num_args: int

    def __init__(self, dunder_name: str, num_args: int = 1):
        assert num_args > 0
        self.dunder_name = dunder_name
        self.num_args = num_args

    def synthesize(self, args: list[ast.expr]) -> tuple[ast.expr, Type]:
        check_num_args(self.num_args, len(args), self.node)
        fst, *rest = args
        return ExprSynthesizer(self.ctx).synthesize_instance_func(
            fst,
            rest,
            self.dunder_name,
            f"a valid argument to `{self.func.name}`",
            give_reason=True,
        )


class CallableChecker(CustomCallChecker):
    """Call checker for the builtin `callable` function"""

    def synthesize(self, args: list[ast.expr]) -> tuple[ast.expr, Type]:
        check_num_args(1, len(args), self.node)
        [arg] = args
        arg, ty = ExprSynthesizer(self.ctx).synthesize(arg)
        is_callable = (
            isinstance(ty, FunctionType)
            or self.ctx.globals.get_instance_func(ty, "__call__") is not None
        )
        const = with_loc(self.node, ast.Constant(value=is_callable))
        return const, bool_type()


class ArrayLenChecker(CustomCallChecker):
    """Function call checker for the `array.__len__` function."""

    @staticmethod
    def _get_const_len(inst: Inst) -> ast.expr:
        """Helper function to extract the static length from the inferred type args."""
        # TODO: This will stop working once we allow generic function defs. Then, the
        #  argument could also just be variable instead of a concrete number.
        match inst:
            case [_, ConstArg(const=ConstValue(value=int(n)))]:
                return ast.Constant(value=n)
        raise InternalGuppyError(f"array.__len__: Invalid instantiation: {inst}")

    def synthesize(self, args: list[ast.expr]) -> tuple[ast.expr, Type]:
        _, _, inst = synthesize_call(self.func.ty, args, self.node, self.ctx)
        return self._get_const_len(inst), int_type()

    def check(self, args: list[ast.expr], ty: Type) -> tuple[ast.expr, Subst]:
        _, subst, inst = check_call(self.func.ty, args, ty, self.node, self.ctx)
        return self._get_const_len(inst), subst


class NewArrayChecker(CustomCallChecker):
    """Function call checker for the `array.__new__` function."""

    @dataclass(frozen=True)
    class InferenceError(Error):
        title: ClassVar[str] = "Cannot infer type"
        span_label: ClassVar[str] = "Cannot infer the type of this array"

        @dataclass(frozen=True)
        class Suggestion(Note):
            message: ClassVar[str] = (
                "Consider adding a type annotation: `x: array[???] = ...`"
            )

    def synthesize(self, args: list[ast.expr]) -> tuple[ast.expr, Type]:
        if len(args) == 0:
            err = NewArrayChecker.InferenceError(self.node)
            err.add_sub_diagnostic(NewArrayChecker.InferenceError.Suggestion(None))
            raise GuppyTypeError(err)
        [fst, *rest] = args
        fst, ty = ExprSynthesizer(self.ctx).synthesize(fst)
        checker = ExprChecker(self.ctx)
        for i in range(len(rest)):
            rest[i], subst = checker.check(rest[i], ty)
            assert len(subst) == 0, "Array element type is closed"
        result_ty = array_type(ty, len(args))
        call = GlobalCall(
            def_id=self.func.id, args=[fst, *rest], type_args=result_ty.args
        )
        return with_loc(self.node, call), result_ty

    def check(self, args: list[ast.expr], ty: Type) -> tuple[ast.expr, Subst]:
        if not is_array_type(ty):
            dummy_array_ty = array_type_def.check_instantiate(
                [p.to_existential()[0] for p in array_type_def.params],
                self.ctx.globals,
                self.node,
            )
            raise GuppyTypeError(TypeMismatchError(self.node, ty, dummy_array_ty))
        match ty.args:
            case [TypeArg(ty=elem_ty), ConstArg(ConstValue(value=int(length)))]:
                subst: Subst = {}
                checker = ExprChecker(self.ctx)
                for i in range(len(args)):
                    args[i], s = checker.check(args[i], elem_ty.substitute(subst))
                    subst |= s
                if len(args) != length:
                    raise GuppyTypeError(
                        TypeMismatchError(self.node, ty, array_type(elem_ty, len(args)))
                    )
                call = GlobalCall(def_id=self.func.id, args=args, type_args=ty.args)
                return with_loc(self.node, call), subst
            case type_args:
                raise InternalGuppyError(f"Invalid array type args: {type_args}")


#: Maximum length of a tag in the `result` function.
TAG_MAX_LEN = 200


class ResultChecker(CustomCallChecker):
    """Call checker for the `result` function."""

    @dataclass(frozen=True)
    class InvalidError(Error):
        title: ClassVar[str] = "Invalid Result"
        span_label: ClassVar[str] = "Expression of type `{ty}` is not a valid result."
        ty: Type

        @dataclass(frozen=True)
        class Explanation(Note):
            message: ClassVar[str] = (
                "Only numeric values or arrays thereof are allowed as results"
            )

    @dataclass(frozen=True)
    class TooLongError(Error):
        title: ClassVar[str] = "Tag too long"
        span_label: ClassVar[str] = "Result tag is too long"

        @dataclass(frozen=True)
        class Hint(Note):
            message: ClassVar[str] = f"Result tags are limited to {TAG_MAX_LEN} bytes"

    def synthesize(self, args: list[ast.expr]) -> tuple[ast.expr, Type]:
        check_num_args(2, len(args), self.node)
        [tag, value] = args
        if not isinstance(tag, ast.Constant) or not isinstance(tag.value, str):
            raise GuppyTypeError(ExpectedError(tag, "a string literal"))
        if len(tag.value.encode("utf-8")) > TAG_MAX_LEN:
            err: Error = ResultChecker.TooLongError(tag)
            err.add_sub_diagnostic(ResultChecker.TooLongError.Hint(None))
            raise GuppyTypeError(err)
        value, ty = ExprSynthesizer(self.ctx).synthesize(value)
        # We only allow numeric values or vectors of numeric values
        err = ResultChecker.InvalidError(value, ty)
        err.add_sub_diagnostic(ResultChecker.InvalidError.Explanation(None))
        if self._is_numeric_or_bool_type(ty):
            base_ty = ty
            array_len: Const | None = None
        elif is_array_type(ty):
            [ty_arg, len_arg] = ty.args
            assert isinstance(ty_arg, TypeArg)
            assert isinstance(len_arg, ConstArg)
            if not self._is_numeric_or_bool_type(ty_arg.ty):
                raise GuppyError(err)
            base_ty = ty_arg.ty
            array_len = len_arg.const
        else:
            raise GuppyError(err)
        node = ResultExpr(value, base_ty, array_len, tag.value)
        return with_loc(self.node, node), NoneType()

    def check(self, args: list[ast.expr], ty: Type) -> tuple[ast.expr, Subst]:
        expr, res_ty = self.synthesize(args)
        subst, _ = check_type_against(res_ty, ty, self.node)
        return expr, subst

    @staticmethod
    def _is_numeric_or_bool_type(ty: Type) -> bool:
        return isinstance(ty, NumericType) or is_bool_type(ty)


class RangeChecker(CustomCallChecker):
    """Call checker for the `range` function."""

    def synthesize(self, args: list[ast.expr]) -> tuple[ast.expr, Type]:
        check_num_args(1, len(args), self.node)
        [stop] = args
        stop, _ = ExprChecker(self.ctx).check(stop, int_type(), "argument")
        range_iter, range_ty = self.make_range(stop)
        if isinstance(stop, ast.Constant):
            return to_sized_iter(range_iter, range_ty, stop.value, self.ctx)
        return range_iter, range_ty

    def range_ty(self) -> StructType:
        from guppylang.std.builtins import Range

        def_id = cast(RawStructDef, Range).id
        range_type_def = self.ctx.globals.defs[def_id]
        assert isinstance(range_type_def, CheckedStructDef)
        return StructType([], range_type_def)

    def make_range(self, stop: ast.expr) -> tuple[ast.expr, Type]:
        make_range = self.ctx.globals.get_instance_func(self.range_ty(), "__new__")
        assert make_range is not None
        start = with_type(int_type(), with_loc(self.node, ast.Constant(value=0)))
        return make_range.synthesize_call([start, stop], self.node, self.ctx)


def to_sized_iter(
    iterator: ast.expr, range_ty: Type, size: int, ctx: Context
) -> tuple[ast.expr, Type]:
    """Adds a static size annotation to an iterator."""
    sized_iter_ty = sized_iter_type(range_ty, size)
    make_sized_iter = ctx.globals.get_instance_func(sized_iter_ty, "__new__")
    assert make_sized_iter is not None
    sized_iter, _ = make_sized_iter.check_call([iterator], sized_iter_ty, iterator, ctx)
    return sized_iter, sized_iter_ty