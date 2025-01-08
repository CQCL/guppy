import ast
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import hugr.build.function as hf
import hugr.tys as ht
from hugr import Wire
from hugr.build.dfg import DefinitionBuilder, OpVar
from hugr.package import FuncDefnPointer

from guppylang.ast_util import AstNode, with_loc
from guppylang.checker.core import Context, Globals, PyScope
from guppylang.checker.expr_checker import (
    check_call,
    synthesize_call,
)
from guppylang.checker.func_checker import (
    check_signature,
)
from guppylang.compiler.core import CompiledGlobals, DFContainer
from guppylang.definition.common import (
    CompilableDef,
    ParsableDef,
)
from guppylang.definition.function import parse_py_func
from guppylang.definition.value import CallableDef, CallReturnWires, CompiledCallableDef
from guppylang.nodes import GlobalCall
from guppylang.span import SourceMap
from guppylang.tys.subst import Inst, Subst
from guppylang.tys.ty import FunctionType, Type, type_to_row

PyFunc = Callable[..., Any]


@dataclass(frozen=True)
class RawTracedFunctionDef(ParsableDef):
    python_func: PyFunc
    python_scope: PyScope

    description: str = field(default="function", init=False)

    def parse(self, globals: Globals, sources: SourceMap) -> "TracedFunctionDef":
        """Parses and checks the user-provided signature of the function."""
        func_ast, _docstring = parse_py_func(self.python_func, sources)
        ty = check_signature(func_ast, globals.with_python_scope(self.python_scope))
        return TracedFunctionDef(
            self.id, self.name, func_ast, ty, self.python_func, self.python_scope
        )

    def compile(self) -> FuncDefnPointer:
        from guppylang.decorator import guppy

        return guppy.compile_function(self)


@dataclass(frozen=True)
class TracedFunctionDef(RawTracedFunctionDef, CallableDef, CompilableDef):
    python_func: PyFunc
    ty: FunctionType
    defined_at: ast.FunctionDef

    def check_call(
        self, args: list[ast.expr], ty: Type, node: AstNode, ctx: Context
    ) -> tuple[ast.expr, Subst]:
        """Checks the return type of a function call against a given type."""
        # Use default implementation from the expression checker
        args, subst, inst = check_call(self.ty, args, ty, node, ctx)
        node = with_loc(node, GlobalCall(def_id=self.id, args=args, type_args=inst))
        return node, subst

    def synthesize_call(
        self, args: list[ast.expr], node: AstNode, ctx: Context
    ) -> tuple[ast.expr, Type]:
        """Synthesizes the return type of a function call."""
        # Use default implementation from the expression checker
        args, ty, inst = synthesize_call(self.ty, args, node, ctx)
        node = with_loc(node, GlobalCall(def_id=self.id, args=args, type_args=inst))
        return node, ty

    def compile_outer(
        self, module: DefinitionBuilder[OpVar]
    ) -> "CompiledTracedFunctionDef":
        """Adds a Hugr `FuncDefn` node for this function to the Hugr.

        Note that we don't compile the function body at this point since we don't have
        access to the other compiled functions yet. The body is compiled later in
        `CompiledFunctionDef.compile_inner()`.
        """
        func_type = self.ty.to_hugr_poly()
        func_def = module.define_function(
            self.name, func_type.body.input, func_type.body.output, func_type.params
        )
        return CompiledTracedFunctionDef(
            self.id,
            self.name,
            self.defined_at,
            self.ty,
            self.python_func,
            self.python_scope,
            func_def,
        )


@dataclass(frozen=True)
class CompiledTracedFunctionDef(TracedFunctionDef, CompiledCallableDef):
    func_def: hf.Function

    def load_with_args(
        self,
        type_args: Inst,
        dfg: DFContainer,
        globals: CompiledGlobals,
        node: AstNode,
    ) -> Wire:
        """Loads the function as a value into a local Hugr dataflow graph."""
        func_ty: ht.FunctionType = self.ty.instantiate(type_args).to_hugr()
        type_args: list[ht.TypeArg] = [arg.to_hugr() for arg in type_args]
        return dfg.builder.load_function(self.func_def, func_ty, type_args)

    def compile_call(
        self,
        args: list[Wire],
        type_args: Inst,
        dfg: DFContainer,
        globals: CompiledGlobals,
        node: AstNode,
    ) -> CallReturnWires:
        """Compiles a call to the function."""
        func_ty: ht.FunctionType = self.ty.instantiate(type_args).to_hugr()
        type_args: list[ht.TypeArg] = [arg.to_hugr() for arg in type_args]
        num_returns = len(type_to_row(self.ty.output))
        call = dfg.builder.call(
            self.func_def, *args, instantiation=func_ty, type_args=type_args
        )
        return CallReturnWires(
            regular_returns=list(call[:num_returns]),
            inout_returns=list(call[num_returns:]),
        )

    def compile_inner(self, globals: CompiledGlobals) -> None:
        """Compiles the body of the function by tracing it."""
        from guppylang.tracing.function import trace_function

        trace_function(
            self.python_func, self.ty, self.func_def, globals, self.defined_at
        )
