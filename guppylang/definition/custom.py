import ast
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from hugr.serialization import ops

from guppylang.ast_util import AstNode, get_type, with_loc, with_type
from guppylang.checker.core import Context, Globals
from guppylang.checker.expr_checker import check_call, synthesize_call
from guppylang.checker.func_checker import check_signature
from guppylang.compiler.core import CompiledGlobals, DFContainer
from guppylang.definition.common import ParsableDef
from guppylang.definition.value import CompiledCallableDef
from guppylang.error import GuppyError, InternalGuppyError
from guppylang.hugr_builder.hugr import Hugr, OutPortV
from guppylang.nodes import GlobalCall
from guppylang.tys.subst import Inst, Subst
from guppylang.tys.ty import FunctionType, NoneType, Type, type_to_row


@dataclass(frozen=True)
class RawCustomFunctionDef(ParsableDef):
    """A raw custom function definition provided by the user.

    Custom functions provide their own checking and compilation logic using a
    `CustomCallChecker` and a `CustomCallCompiler`.

    The raw definition stores exactly what the user has written (i.e. the AST together
    with the provided checker and compiler), without inspecting the signature.
    """

    defined_at: ast.FunctionDef
    call_checker: "CustomCallChecker"
    call_compiler: "CustomCallCompiler"

    # Whether the function may be used as a higher-order value. This is only possible
    # if a static type for the function is provided.
    higher_order_value: bool

    description: str = field(default="function", init=False)

    def parse(self, globals: "Globals") -> "CustomFunctionDef":
        """Parses and checks the user-provided signature of the custom function.

        The signature is optional if custom type checking logic is provided by the user.
        However, note that the signature annotation is required, if we want to use the
        function as a higher-order value.

        If no signature is provided, we fill in the dummy signature `() -> ()`. This
        type will never be inspected, since we rely on the provided custom checking
        code. The only information we need to access is that it's a function type and
        that there are no unsolved existential vars.
        """
        # Type annotations are needed if we rely on the default call checker or want
        # to allow the usage of the function as a higher-order value
        requires_type_annotation = (
            isinstance(self.call_checker, DefaultCallChecker) or self.higher_order_value
        )
        has_type_annotation = self.defined_at.returns or any(
            arg.annotation for arg in self.defined_at.args.args
        )

        if requires_type_annotation and not has_type_annotation:
            raise GuppyError(
                f"Type signature for function `{self.name}` is required. "
                "Alternatively, try passing `higher_order_value=False` on definition.",
                self.defined_at,
            )

        ty = (
            check_signature(self.defined_at, globals)
            if requires_type_annotation
            else FunctionType([], NoneType())
        )
        return CustomFunctionDef(
            self.id,
            self.name,
            self.defined_at,
            ty,
            self.call_checker,
            self.call_compiler,
            self.higher_order_value,
        )

    def compile_call(
        self,
        args: list[OutPortV],
        type_args: Inst,
        dfg: DFContainer,
        graph: Hugr,
        globals: CompiledGlobals,
        node: AstNode,
    ) -> list[OutPortV]:
        """Compiles a call to the function."""
        self.call_compiler._setup(type_args, dfg, graph, globals, node)
        return self.call_compiler.compile(args)


@dataclass(frozen=True)
class CustomFunctionDef(CompiledCallableDef):
    """A custom function with parsed and checked signature."""

    defined_at: AstNode
    call_checker: "CustomCallChecker"
    call_compiler: "CustomCallCompiler"
    ty: FunctionType
    higher_order_value: bool

    description: str = field(default="function", init=False)

    def check_call(
        self, args: list[ast.expr], ty: Type, node: AstNode, ctx: Context
    ) -> tuple[ast.expr, Subst]:
        """Checks the return type of a function call against a given type.

        This is done by invoking the provided `CustomCallChecker`.
        """
        self.call_checker._setup(ctx, node, self)
        new_node, subst = self.call_checker.check(args, ty)
        return with_type(ty, with_loc(node, new_node)), subst

    def synthesize_call(
        self, args: list[ast.expr], node: AstNode, ctx: "Context"
    ) -> tuple[ast.expr, Type]:
        """Synthesizes the return type of a function call.

        This is done by invoking the provided `CustomCallChecker`.
        """
        self.call_checker._setup(ctx, node, self)
        new_node, ty = self.call_checker.synthesize(args)
        return with_type(ty, with_loc(node, new_node)), ty

    def load_with_args(
        self,
        type_args: Inst,
        dfg: "DFContainer",
        graph: Hugr,
        globals: CompiledGlobals,
        node: AstNode,
    ) -> OutPortV:
        """Loads the custom function as a value into a local dataflow graph.

        This will place a `FunctionDef` node into the Hugr module and loads it into the
        DFG. This operation will fail the function is not allowed to be used as a
        higher-order value.
        """
        # TODO: This should be raised during checking, not compilation!
        if not self.higher_order_value:
            raise GuppyError(
                "This function does not support usage in a higher-order context",
                node,
            )
        assert len(self.ty.params) == len(type_args)

        # We create a `FunctionDef` that takes some inputs, compiles a call to the
        # function, and returns the results. If the function signature is polymorphic,
        # we explicitly monomorphise here and invoke the call compiler with the
        # inferred type args.
        fun_ty = self.ty.instantiate(type_args)
        def_node = graph.add_def(fun_ty, dfg.node, self.name, self.defined_at)
        with graph.parent(def_node):
            _, inp_ports = graph.add_input_with_ports(list(fun_ty.inputs))
            returns = self.compile_call(
                inp_ports,
                type_args,
                DFContainer(graph, def_node),
                graph,
                globals,
                node,
            )
            graph.add_output(returns)

        # Finally, load the function into the local DFG. We already monomorphised, so we
        # can load with empty type args
        return graph.add_load_function(def_node.out_port(0), [], dfg.node).out_port(0)

    def compile_call(
        self,
        args: list[OutPortV],
        type_args: Inst,
        dfg: DFContainer,
        graph: Hugr,
        globals: CompiledGlobals,
        node: AstNode,
    ) -> list[OutPortV]:
        """Compiles a call to the function."""
        self.call_compiler._setup(type_args, dfg, graph, globals, node)
        return self.call_compiler.compile(args)


class CustomCallChecker(ABC):
    """Abstract base class for custom function call type checkers."""

    ctx: Context
    node: AstNode
    func: CustomFunctionDef

    def _setup(self, ctx: Context, node: AstNode, func: CustomFunctionDef) -> None:
        self.ctx = ctx
        self.node = node
        self.func = func

    @abstractmethod
    def check(self, args: list[ast.expr], ty: Type) -> tuple[ast.expr, Subst]:
        """Checks the return value against a given type.

        Returns a (possibly) transformed and annotated AST node for the call.
        """

    @abstractmethod
    def synthesize(self, args: list[ast.expr]) -> tuple[ast.expr, Type]:
        """Synthesizes a type for the return value of a call.

        Also returns a (possibly) transformed and annotated argument list.
        """


class CustomCallCompiler(ABC):
    """Abstract base class for custom function call compilers."""

    type_args: Inst
    dfg: DFContainer
    graph: Hugr
    globals: CompiledGlobals
    node: AstNode

    def _setup(
        self,
        type_args: Inst,
        dfg: DFContainer,
        graph: Hugr,
        globals: CompiledGlobals,
        node: AstNode,
    ) -> None:
        self.type_args = type_args
        self.dfg = dfg
        self.graph = graph
        self.globals = globals
        self.node = node

    @abstractmethod
    def compile(self, args: list[OutPortV]) -> list[OutPortV]:
        """Compiles a custom function call and returns the resulting ports."""


class DefaultCallChecker(CustomCallChecker):
    """Checks function calls by comparing to a type signature."""

    def check(self, args: list[ast.expr], ty: Type) -> tuple[ast.expr, Subst]:
        # Use default implementation from the expression checker
        args, subst, inst = check_call(self.func.ty, args, ty, self.node, self.ctx)
        return GlobalCall(def_id=self.func.id, args=args, type_args=inst), subst

    def synthesize(self, args: list[ast.expr]) -> tuple[ast.expr, Type]:
        # Use default implementation from the expression checker
        args, ty, inst = synthesize_call(self.func.ty, args, self.node, self.ctx)
        return GlobalCall(def_id=self.func.id, args=args, type_args=inst), ty


class NotImplementedCallCompiler(CustomCallCompiler):
    """Call compiler for custom functions that are already lowered during checking.

    For example, the custom checker could replace the call with a series of calls to
    other functions. In that case, the original function will no longer be present and
    thus doesn't need to be compiled.
    """

    def compile(self, args: list[OutPortV]) -> list[OutPortV]:
        raise InternalGuppyError("Function should have been removed during checking")


class OpCompiler(CustomCallCompiler):
    """Call compiler for functions that are directly implemented via Hugr ops."""

    op: ops.OpType

    def __init__(self, op: ops.OpType) -> None:
        self.op = op

    def compile(self, args: list[OutPortV]) -> list[OutPortV]:
        node = self.graph.add_node(
            self.op.model_copy(deep=True),
            inputs=args,
            parent=self.dfg.node,
            debug=self.node,
        )
        return_ty = get_type(self.node)
        return [node.add_out_port(ty) for ty in type_to_row(return_ty)]


class NoopCompiler(CustomCallCompiler):
    """Call compiler for functions that are noops."""

    def compile(self, args: list[OutPortV]) -> list[OutPortV]:
        return args
