from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from hugr import ops
from hugr.build.dfg import DfBase

from guppylang.ast_util import AstNode, with_loc, with_type
from guppylang.cfg.builder import tmp_vars
from guppylang.checker.core import Context, Locals, Variable
from guppylang.checker.errors.type_errors import TypeMismatchError
from guppylang.compiler.core import CompiledGlobals, DFContainer
from guppylang.compiler.expr_compiler import ExprCompiler
from guppylang.definition.value import CompiledCallableDef
from guppylang.diagnostic import Error
from guppylang.error import GuppyError, exception_hook
from guppylang.nodes import PlaceNode
from guppylang.tracing.object import GuppyObject
from guppylang.tracing.state import (
    TracingState,
    get_tracing_globals,
    get_tracing_state,
    set_tracing_state,
)
from guppylang.tracing.unpacking import (
    P,
    guppy_object_from_py,
    repack_guppy_object,
    unpack_guppy_object,
    update_packed_value,
)
from guppylang.tracing.util import tracing_except_hook
from guppylang.tys.ty import FunctionType, InputFlags, type_to_row

if TYPE_CHECKING:
    import ast

    from hugr import Wire


@dataclass(frozen=True)
class TracingReturnLinearityViolationError(Error):
    title: ClassVar[str] = "Linearity violation in function return"
    message: ClassVar[str] = "{msg}"
    msg: str


def trace_function(
    python_func: Callable[..., Any],
    ty: FunctionType,
    builder: DfBase[P],
    globals: CompiledGlobals,
    node: AstNode,
) -> None:
    """Kicks off tracing of a function."""
    state = TracingState(globals, DFContainer(builder, {}), node)
    with set_tracing_state(state):
        inputs = [
            unpack_guppy_object(GuppyObject(inp.ty, wire), builder)
            for wire, inp in zip(builder.inputs(), ty.inputs, strict=False)
        ]

        with exception_hook(tracing_except_hook):
            py_out = python_func(*inputs)

        try:
            out_obj = repack_guppy_object(py_out, builder)
        except ValueError as err:
            # Linearity violation in the return statement
            raise GuppyError(
                TracingReturnLinearityViolationError(node, str(err))
            ) from None

        # Check that the output type is correct
        if out_obj._ty != ty.output:
            raise GuppyError(
                TypeMismatchError(node, ty.output, out_obj._ty, "return value")
            )

        # Unpack regular returns
        out_tys = type_to_row(out_obj._ty)
        if len(out_tys) > 1:
            regular_returns: list[Wire] = list(
                builder.add_op(ops.UnpackTuple(), out_obj._use_wire(None)).outputs()
            )
        elif len(out_tys) > 0:
            regular_returns = [out_obj._use_wire(None)]
        else:
            regular_returns = []

        # Compute the inout extra outputs
        try:
            inout_returns = [
                repack_guppy_object(inout_obj, builder)._use_wire(None)
                for inout_obj, inp in zip(inputs, ty.inputs, strict=False)
                if InputFlags.Inout in inp.flags
            ]
        except ValueError as err:
            raise GuppyError(
                TracingReturnLinearityViolationError(node, str(err))
            ) from None

    # Check that all allocated linear objects have been used
    if state.unused_objs:
        unused = state.allocated_objs[state.unused_objs.pop()]
        msg = f"Value with linear type `{unused._ty}` is leaked by this function"
        raise GuppyError(TracingReturnLinearityViolationError(node, msg)) from None

    builder.set_outputs(*regular_returns, *inout_returns)


def trace_call(func: CompiledCallableDef, *args: Any) -> Any:
    state = get_tracing_state()
    globals = get_tracing_globals()
    assert func.defined_at is not None

    # Try to turn args into `GuppyObjects`
    args_objs = [
        guppy_object_from_py(arg, state.dfg.builder, state.node) for arg in args
    ]

    # Create dummy variables and bind the objects to them
    arg_vars = [Variable(next(tmp_vars), obj._ty, None) for obj in args_objs]
    locals = Locals({var.name: var for var in arg_vars})
    for obj, var in zip(args_objs, arg_vars, strict=False):
        state.dfg[var] = obj._use_wire(func)

    # Check call
    arg_exprs: list[ast.expr] = [
        with_loc(func.defined_at, with_type(var.ty, PlaceNode(var))) for var in arg_vars
    ]
    call_node, ret_ty = func.synthesize_call(
        arg_exprs, func.defined_at, Context(globals, locals, {})
    )

    # Compile call
    ret_wire = ExprCompiler(state.globals).compile(call_node, state.dfg)

    # Update inouts
    for inp, arg, var in zip(func.ty.inputs, args, arg_vars, strict=False):
        if InputFlags.Inout in inp.flags:
            inout_wire = state.dfg[var]
            update_packed_value(arg, GuppyObject(inp.ty, inout_wire), state.dfg.builder)

    return GuppyObject(ret_ty, ret_wire)
