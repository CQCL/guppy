import hugr
from hugr import Wire, ops
from hugr import tys as ht
from hugr import val as hv
from hugr.dfg import _DfBase
from hugr.std.float import FLOAT_T

from guppylang.definition.custom import (
    CustomCallCompiler,
)
from guppylang.definition.value import CallReturnWires
from guppylang.error import InternalGuppyError
from guppylang.tys.arg import ConstArg, TypeArg
from guppylang.tys.builtin import array_type
from guppylang.tys.const import ConstValue
from guppylang.tys.ty import NumericType

# Note: Hugr's INT_T is 64bits, but guppy defaults to 32bits
INT_T = NumericType(NumericType.Kind.Int).to_hugr()


class NatTruedivCompiler(CustomCallCompiler):
    """Compiler for the `nat.__truediv__` method."""

    def compile(self, args: list[Wire]) -> list[Wire]:
        from guppylang.prelude.builtins import Float, Nat

        # Compile `truediv` using float arithmetic
        [left, right] = args
        [left] = Nat.__float__.compile_call(
            [left],
            [],
            self.dfg,
            self.globals,
            self.node,
            ht.FunctionType([INT_T], [FLOAT_T]),
        )
        [right] = Nat.__float__.compile_call(
            [right],
            [],
            self.dfg,
            self.globals,
            self.node,
            ht.FunctionType([INT_T], [FLOAT_T]),
        )
        [out] = Float.__truediv__.compile_call(
            [left, right],
            [],
            self.dfg,
            self.globals,
            self.node,
            ht.FunctionType([FLOAT_T, FLOAT_T], [FLOAT_T]),
        )
        return [out]


class IntTruedivCompiler(CustomCallCompiler):
    """Compiler for the `int.__truediv__` method."""

    def compile(self, args: list[Wire]) -> list[Wire]:
        from guppylang.prelude.builtins import Float, Int

        # Compile `truediv` using float arithmetic
        [left, right] = args
        [left] = Int.__float__.compile_call(
            [left],
            [],
            self.dfg,
            self.globals,
            self.node,
            ht.FunctionType([INT_T], [FLOAT_T]),
        )
        [right] = Int.__float__.compile_call(
            [right],
            [],
            self.dfg,
            self.globals,
            self.node,
            ht.FunctionType([INT_T], [FLOAT_T]),
        )
        [out] = Float.__truediv__.compile_call(
            [left, right],
            [],
            self.dfg,
            self.globals,
            self.node,
            ht.FunctionType([FLOAT_T, FLOAT_T], [FLOAT_T]),
        )
        return [out]


class FloatBoolCompiler(CustomCallCompiler):
    """Compiler for the `float.__bool__` method."""

    def compile(self, args: list[Wire]) -> list[Wire]:
        from guppylang.prelude.builtins import Float

        # We have: bool(x) = (x != 0.0)
        zero = self.builder.load(hugr.std.float.FloatVal(0.0))
        [out] = Float.__ne__.compile_call(
            [args[0], zero],
            [],
            self.dfg,
            self.globals,
            self.node,
            ht.FunctionType([FLOAT_T, FLOAT_T], [ht.Bool]),
        )
        return [out]


class FloatFloordivCompiler(CustomCallCompiler):
    """Compiler for the `float.__floordiv__` method."""

    def compile(self, args: list[Wire]) -> list[Wire]:
        from guppylang.prelude.builtins import Float

        # We have: floordiv(x, y) = floor(truediv(x, y))
        [div] = Float.__truediv__.compile_call(
            args,
            [],
            self.dfg,
            self.globals,
            self.node,
            ht.FunctionType([FLOAT_T, FLOAT_T], [FLOAT_T]),
        )
        [floor] = Float.__floor__.compile_call(
            [div],
            [],
            self.dfg,
            self.globals,
            self.node,
            ht.FunctionType([FLOAT_T], [FLOAT_T]),
        )
        return [floor]


class FloatModCompiler(CustomCallCompiler):
    """Compiler for the `float.__mod__` method."""

    def compile(self, args: list[Wire]) -> list[Wire]:
        from guppylang.prelude.builtins import Float

        # We have: mod(x, y) = x - (x // y) * y
        [div] = Float.__floordiv__.compile_call(
            args,
            [],
            self.dfg,
            self.globals,
            self.node,
            ht.FunctionType([FLOAT_T] * len(args), [FLOAT_T]),
        )
        [mul] = Float.__mul__.compile_call(
            [div, args[1]],
            [],
            self.dfg,
            self.globals,
            self.node,
            ht.FunctionType([FLOAT_T, FLOAT_T], [FLOAT_T]),
        )
        [sub] = Float.__sub__.compile_call(
            [args[0], mul],
            [],
            self.dfg,
            self.globals,
            self.node,
            ht.FunctionType([FLOAT_T, FLOAT_T], [FLOAT_T]),
        )
        return [sub]


class FloatDivmodCompiler(CustomCallCompiler):
    """Compiler for the `__divmod__` method."""

    def compile(self, args: list[Wire]) -> list[Wire]:
        from guppylang.prelude.builtins import Float

        # We have: divmod(x, y) = (div(x, y), mod(x, y))
        [div] = Float.__truediv__.compile_call(
            args,
            [],
            self.dfg,
            self.globals,
            self.node,
            ht.FunctionType([FLOAT_T, FLOAT_T], [FLOAT_T]),
        )
        [mod] = Float.__mod__.compile_call(
            args,
            [],
            self.dfg,
            self.globals,
            self.node,
            ht.FunctionType([FLOAT_T] * len(args), [FLOAT_T]),
        )
        return list(self.builder.add(ops.MakeTuple()(div, mod)))


class NewArrayCompiler(CustomCallCompiler):
    """Compiler for the `array.__new__` function."""

    def compile(self, args: list[Wire]) -> list[Wire]:
        match self.type_args:
            case [
                TypeArg(ty=elem_ty) as ty_arg,
                ConstArg(ConstValue(value=int(length))) as len_arg,
            ]:
                sig = ht.FunctionType(
                    [elem_ty.to_hugr()] * len(args),
                    [array_type(elem_ty, length).to_hugr()],
                )
                op = ops.Custom(
                    extension="prelude",
                    signature=sig,
                    name="new_array",
                    args=[len_arg.to_hugr(), ty_arg.to_hugr()],
                )
                return [self.builder.add_op(op, *args)]
            case type_args:
                raise InternalGuppyError(f"Invalid array type args: {type_args}")


class MeasureCompiler(CustomCallCompiler):
    """Compiler for the `measure` function."""

    def compile(self, args: list[Wire]) -> list[Wire]:
        from guppylang.prelude.quantum import quantum_op

        [q] = args
        [q, bit] = self.builder.add_op(
            quantum_op("Measure")(ht.FunctionType([ht.Qubit], [ht.Qubit, ht.Bool]), []),
            q,
        )
        self.builder.add_op(quantum_op("QFree")(ht.FunctionType([ht.Qubit], []), []), q)
        return [bit]


class QAllocCompiler(CustomCallCompiler):
    """Compiler for the `qubit` function."""

    def compile(self, args: list[Wire]) -> list[Wire]:
        from guppylang.prelude.quantum import quantum_op

        assert not args, "qubit() does not take any arguments"
        q = self.builder.add_op(
            quantum_op("QAlloc")(ht.FunctionType([], [ht.Qubit]), [])
        )
        q = self.builder.add_op(
            quantum_op("Reset")(ht.FunctionType([ht.Qubit], [ht.Qubit]), []), q
        )
        return [q]


class ArrayGetitemCompiler(CustomCallCompiler):
    """Compiler for the `array.__getitem__` function."""

    def build_classical_getitem(
        self,
        array: Wire,
        array_ty: ht.Type,
        idx: Wire,
        idx_ty: ht.Type,
        elem_ty: ht.Type,
    ) -> CallReturnWires:
        """Lowers a call to `array.__getitem__` for classical arrays."""
        [ty_arg, len_arg] = self.type_args
        op = ops.Custom(
            extension="guppy.unsupported.array",
            signature=ht.FunctionType([array_ty, idx_ty], [array_ty, elem_ty]),
            name="get",
            args=[len_arg.to_hugr(), ty_arg.to_hugr()],
        )
        node = self.builder.add_op(op, array, idx)
        return CallReturnWires(regular_returns=[node[1]], inout_returns=[node[0]])

    def build_linear_getitem(
        self,
        array: Wire,
        array_ty: ht.Type,
        idx: Wire,
        idx_ty: ht.Type,
        elem_ty: ht.Type,
    ) -> CallReturnWires:
        """Lowers a call to `array.__getitem__` for linear arrays."""
        # Swap out the element at the given index with `None`. The `to_hugr`
        # implementation of the array type ensures that linear element types are turned
        # into optionals.
        elem_opt_ty = ht.Sum([[elem_ty], []])
        none = self.builder.add_op(ops.Tag(1, elem_opt_ty))
        length = self.type_args[1].to_hugr()
        array, elem_opt = build_array_set(
            self.builder,
            array,
            array_ty,
            idx,
            idx_ty,
            none,
            elem_opt_ty,
            length,
        )
        # Make sure that the element we got out is not None
        conditional = self.builder.add_conditional(elem_opt)
        with conditional.add_case(0) as case:
            case.set_outputs(*case.inputs())
        with conditional.add_case(1) as case:
            error = build_error(case, 1, "Linear array element has already been used")
            case.set_outputs(build_panic(case, [], [elem_ty], error))
        return CallReturnWires(regular_returns=[conditional], inout_returns=[array])

    def compile_with_inouts(self, args: list[Wire]) -> CallReturnWires:
        [array, idx] = args
        [array_ty, idx_ty] = self.ty.input
        [elem_ty, *_] = self.ty.output
        if elem_ty.type_bound() == ht.TypeBound.Any:
            return self.build_linear_getitem(array, array_ty, idx, idx_ty, elem_ty)
        else:
            return self.build_classical_getitem(array, array_ty, idx, idx_ty, elem_ty)

    def compile(self, args: list[Wire]) -> list[Wire]:
        raise InternalGuppyError("Call compile_with_inouts instead")


class ArraySetitemCompiler(CustomCallCompiler):
    """Compiler for the `array.__setitem__` function."""

    def build_classical_setitem(
        self,
        array: Wire,
        array_ty: ht.Type,
        idx: Wire,
        idx_ty: ht.Type,
        elem: Wire,
        elem_ty: ht.Type,
        length: ht.TypeArg,
    ) -> CallReturnWires:
        """Lowers a call to `array.__setitem__` for classical arrays."""
        array, _ = build_array_set(
            self.builder, array, array_ty, idx, idx_ty, elem, elem_ty, length
        )
        return CallReturnWires(regular_returns=[], inout_returns=[array])

    def build_linear_setitem(
        self,
        array: Wire,
        array_ty: ht.Type,
        idx: Wire,
        idx_ty: ht.Type,
        elem: Wire,
        elem_ty: ht.Type,
        length: ht.TypeArg,
    ) -> CallReturnWires:
        """Lowers a call to `array.__setitem__` for linear arrays."""
        # Embed the element into an optional
        elem_opt_ty = ht.Sum([[elem_ty], []])
        elem = self.builder.add_op(ops.Tag(0, elem_opt_ty), elem)
        array, old_elem = build_array_set(
            self.builder, array, array_ty, idx, idx_ty, elem, elem_opt_ty, length
        )
        # Check that the old element was `None`
        conditional = self.builder.add_conditional(old_elem)
        with conditional.add_case(0) as case:
            error = build_error(case, 1, "Linear array element has not been used")
            build_panic(case, [elem_ty], [], error, *case.inputs())
            case.set_outputs()
        with conditional.add_case(1) as case:
            case.set_outputs()
        return CallReturnWires(regular_returns=[], inout_returns=[array])

    def compile_with_inouts(self, args: list[Wire]) -> CallReturnWires:
        [array, idx, elem] = args
        [array_ty, idx_ty, elem_ty] = self.ty.input
        length = self.type_args[1].to_hugr()
        if elem_ty.type_bound() == ht.TypeBound.Any:
            return self.build_linear_setitem(
                array, array_ty, idx, idx_ty, elem, elem_ty, length
            )
        else:
            return self.build_classical_setitem(
                array, array_ty, idx, idx_ty, elem, elem_ty, length
            )

    def compile(self, args: list[Wire]) -> list[Wire]:
        raise InternalGuppyError("Call compile_with_inouts instead")


#: The Hugr error type
error_ty = ht.Opaque(
    id="error", bound=ht.TypeBound.Copyable, args=[], extension="prelude"
)


def build_panic(
    # TODO: Change to `_DfBase[ops.DfParentOp]` once `_DfBase` is covariant
    builder: _DfBase[ops.Case],
    in_tys: ht.TypeRow,
    out_tys: ht.TypeRow,
    err: Wire,
    *args: Wire,
) -> Wire:
    """Builds a panic operation."""
    op = ops.Custom(
        extension="prelude",
        signature=ht.FunctionType([error_ty, *in_tys], out_tys),
        name="panic",
        args=[
            ht.SequenceArg([ht.TypeTypeArg(ty) for ty in in_tys]),
            ht.SequenceArg([ht.TypeTypeArg(ty) for ty in out_tys]),
        ],
    )
    return builder.add_op(op, err, *args)


def build_error(builder: _DfBase[ops.Case], signal: int, msg: str) -> Wire:
    """Constructs and loads a static error value."""
    val = hv.Extension(
        name="ConstError",
        typ=error_ty,
        val={"signal": signal, "message": msg},
        extensions=["prelude"],
    )
    return builder.load(builder.add_const(val))


def build_array_set(
    builder: _DfBase[ops.DfParentOp],
    array: Wire,
    array_ty: ht.Type,
    idx: Wire,
    idx_ty: ht.Type,
    elem: Wire,
    elem_ty: ht.Type,
    length: ht.TypeArg,
) -> tuple[Wire, Wire]:
    """Builds an array set operation, returning the original element."""
    op = ops.Custom(
        extension="guppy.unsupported.array",
        signature=ht.FunctionType([array_ty, idx_ty, elem_ty], [array_ty, elem_ty]),
        name="get",
        args=[length, ht.TypeTypeArg(elem_ty)],
    )
    array, swapped_elem = iter(builder.add_op(op, array, idx, elem))
    return array, swapped_elem


class RangeCompiler(CustomCallCompiler):
    def compile(self, args: list[Wire]) -> list[Wire]:
        from typing import cast

        from guppylang.compiler.expr_compiler import python_value_to_hugr
        from guppylang.definition.custom import CustomFunctionDef

        # Find the builtins module. Brute-force search!
        # (But we hope this to be quick as we expect most entries to be in builtins)
        builtins = next(
            def_id.module
            for def_id in self.globals
            if def_id.module is not None and def_id.module.name == "builtins"
        )
        id_Range = builtins._globals["Range"].id
        id_new = builtins._globals.impls[id_Range]["__new__"]
        ty = NumericType(NumericType.Kind.Int)
        if len(args) == 1:
            const0 = python_value_to_hugr(0, ty)
            assert const0 is not None
            args.insert(0, self.builder.load(const0))
        if len(args) == 2:
            const1 = python_value_to_hugr(1, ty)
            assert const1 is not None
            args.append(self.builder.load(const1))
        # python would raise ValueError if step == 0, we have no way to indicate here
        # so will produce a Range that just repeats its first argument
        call_rets = cast(CustomFunctionDef, self.globals[id_new]).compile_call(
            args, [], self.dfg, self.globals, self.node
        )
        assert len(call_rets.inout_returns) == 0
        return call_rets.regular_returns
