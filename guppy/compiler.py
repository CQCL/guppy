import ast
import inspect
import sys
import textwrap

from abc import ABC
from collections import deque
from dataclasses import field, dataclass
from typing import Callable, Union, Optional, Any

from guppy.hugr.hugr import Hugr, OutPort, Node, DataflowContainingNode
from guppy. guppy_types import (IntType, GuppyType, FloatType, BoolType, RowType, StringType, type_from_python_value,
                                TupleType, FunctionType)
from guppy.visitor import AstVisitor, name_nodes_in_expr

AstNode = Union[ast.AST, ast.operator, ast.expr, ast.arg, ast.stmt, ast.Name, ast.keyword, ast.FunctionDef]


@dataclass(frozen=True)
class SourceLoc:
    """ A source location associated with an AST node.

    This class translates the location data provided by the ast module
    into a location inside the file
    """
    line: int
    col: int
    ast_node: Optional[AstNode]

    @staticmethod
    def from_ast(node: AstNode, line_offset: int) -> "SourceLoc":
        return SourceLoc(line_offset + node.lineno, node.col_offset, node)

    def __str__(self) -> str:
        return f"{self.line}:{self.col}"

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, SourceLoc):
            raise NotImplementedError()
        return (self.line, self.col) < (other.line, other.col)


@dataclass()
class GuppyError(Exception):
    """ General Guppy error tied to a node in the AST. """
    msg: str
    location: Optional[AstNode] = None


class GuppyTypeError(GuppyError):
    """ Special Guppy exception for type errors. """
    pass


class InternalGuppyError(Exception):
    """ Exception for internal problems during compilation. """
    pass


def assert_arith_type(ty: Optional[GuppyType], node: ast.expr) -> None:
    """ Check that a given type is arithmetic, i.e. an integer or float,
    or raise a type error otherwise. """
    if not isinstance(ty, IntType) and not isinstance(ty, FloatType):
        raise GuppyTypeError(f"Expected expression of type `int` or `float`, "
                             f"but got `{ast.unparse(node)}` of type `{ty}`", node)


def assert_int_type(ty: Optional[GuppyType], node: ast.expr) -> None:
    """ Check that a given type is integer or raise a type error otherwise. """
    if not isinstance(ty, IntType):
        raise GuppyTypeError(f"Expected expression of type `int`, "
                             f"but got `{ast.unparse(node)}` of type `{ty}`", node)


def assert_bool_type(ty: Optional[GuppyType], node: ast.expr) -> None:
    """ Check that a given type is boolean or raise a type error otherwise. """
    if not isinstance(ty, BoolType):
        raise GuppyTypeError(f"Expected expression of type `bool`, "
                             f"but got `{ast.unparse(node)}` of type `{ty}`", node)


class UndefinedPort(OutPort):
    """ Dummy port for undefined variables.

    Raises an `InternalGuppyError` if one tries to access one of its properties.
    """
    def __init__(self, ty: Optional[GuppyType]):
        self.ty = ty

    @property
    def node(self) -> Node:  # type: ignore
        raise InternalGuppyError("Tried to access undefined Port")

    @property
    def offset(self) -> int:  # type: ignore
        raise InternalGuppyError("Tried to access undefined Port")


@dataclass(frozen=True)
class Variable:
    """ Class holding all data associated with a variable during compilation.

    Each variable corresponds to a Hugr port. We store the locations where the
    variable was last defined. Furthermore, variables may collect errors during
    compilation that are only raised if the variable is actually used.
    """
    name: str
    port: OutPort
    defined_at: set[SourceLoc]  # Set since variable can be defined in `if` and `else` branches
    errors_on_usage: list[GuppyError] = field(default_factory=list)

    @property
    def ty(self) -> Optional[GuppyType]:
        """ The type of the variable. """
        return self.port.ty


def merge_variables(*vs: Variable, new_port: OutPort) -> Variable:
    """ Merges variables with the same name coming from different control flow paths.

    For example, if a new variable is defined in the if- and else-path of a
    conditional we have to check that the types match up in both cases.
    Additionally, the new port for the merged variable must be passed.
    """
    assert len(vs) > 0
    v = vs[0]
    name, ty, defined_at, errors_on_usage = vs[0].name, v.ty, v.defined_at, v.errors_on_usage
    assert ty == new_port.ty
    for v in vs:
        assert v.name == name
        errors_on_usage += v.errors_on_usage
        if v.ty != ty:
            # TODO: Collect all type mismatches in a single error?
            err = GuppyError(f"Variable `{name}` can refer to different types: "
                             f"`{ty}` (at {', '.join(str(loc) for loc in sorted(vs[0].defined_at))}) vs "
                             f"`{v.ty}` (at {', '.join(str(loc) for loc in sorted(v.defined_at))})")
            errors_on_usage.append(err)
        defined_at |= v.defined_at
    return Variable(name, new_port, defined_at, errors_on_usage)


def type_from_ast(node: ast.expr) -> GuppyType:
    """ Turns an AST expression into a Guppy type. """
    if isinstance(node, ast.Constant) and node.value is None:
        return RowType([])
    elif isinstance(node, ast.Name):
        if node.id == "int":
            return IntType()
        elif node.id == "float":
            return FloatType()
        elif node.id == "bool":
            return BoolType()
        elif node.id == "str":
            return StringType()
    # TODO: Remaining cases
    raise GuppyError(f"Invalid type: `{ast.unparse(node)}`", node)


def is_functional_annotation(stmt: ast.stmt) -> bool:
    """ Returns `True` iff the given statement is the functional pseudo-decorator.

    Pseudo-decorators are built using the matmul operator `@`, i.e. `_@functional`.
    """
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.BinOp):
        op = stmt.value
        if isinstance(op.op, ast.MatMult) and isinstance(op.left, ast.Name) and isinstance(op.right, ast.Name):
            return op.left.id == "_" and op.right.id == "functional"
    return False


# We can treat anything that contains a DFG on Hugr level as a basic block
BBNode = DataflowContainingNode

# A dictionary mapping names to live variables
VarMap = dict[str, Variable]


class CompilerBase(ABC):
    """ Base class for the Guppy compiler.

    Provides utility methods for working with inputs, outputs, DFGs, and blocks.
    """
    graph: Hugr

    def _add_input(self, variables: VarMap, parent: Node) -> VarMap:
        """ Adds an input node with ports for each live variable. """
        # Inputs are ordered lexicographically
        # TODO: Instead we could pass around an explicit variable ordering
        vs = sorted(variables.values(), key=lambda v: v.name)
        inp = self.graph.add_input(output_tys=[v.ty for v in vs], parent=parent)
        new_vars: VarMap = {v.name: Variable(v.name, inp.out_port(i), v.defined_at, v.errors_on_usage)
                            for (i, v) in enumerate(vs)}
        return new_vars

    def _add_output(self, variables: VarMap, parent: Node, extra_outputs: Optional[list[OutPort]] = None) -> None:
        """ Adds an output node and connects all live variables to it.

        Optionally, some extra ports can be prepended before the variables.
        """
        # Outputs are order lexicographically
        # TODO: Instead we could pass around an explicit variable ordering
        vs = sorted(variables.values(), key=lambda v: v.name)
        extra_outputs = extra_outputs or []
        self.graph.add_output(parent=parent, inputs=extra_outputs + [v.port for v in vs])

    def _make_dfg(self, variables: VarMap, parent: Node) -> tuple[DataflowContainingNode, VarMap]:
        """ Creates a `DFG` node with input capturing all live variables.

        Additionally, returns a new variable map for use inside the dataflow grap.
        """
        dfg = self.graph.add_dfg(parent)
        new_vars = self._add_input(variables, dfg)
        return dfg, new_vars

    def _make_case(self, variables: VarMap, parent: Node) -> tuple[DataflowContainingNode, VarMap]:
        """ Creates a `Case`` node with input capturing all live variables.

        Additionally, returns a new variable map for use inside the `Case`
        dataflow graph.
        """
        dfg = self.graph.add_case(parent)
        new_vars = self._add_input(variables, dfg)
        return dfg, new_vars

    def _make_bb(self, predecessor: BBNode, variables: VarMap) -> tuple[BBNode, VarMap]:
        """ Creates a basic block, i.e. a `Block` node with an input capturing
        all live variables and connects it to a control flow predecessor BB.

        Additionally, returns a new variable map for use inside the BB.
        """
        block = self.graph.add_block(predecessor.parent)
        self.graph.add_edge(predecessor.add_out_port(None), block.add_in_port(None))
        new_vars = self._add_input(variables, block)
        return block, new_vars

    def _finish_bb(self, bb: BBNode, variables: Optional[VarMap] = None, outputs: Optional[list[OutPort]] = None,
                   branch_pred: Optional[OutPort] = None) -> None:
        """ Finishes a basic block by adding an output node.

        The outputs of the BB can be given by a variable map, or manually
        specified by a list of ports. If the block branches, an optional
        port holding the branching predicate can be passed.
        """
        assert variables or outputs
        # If the BB doesn't branch, we still need to add a unit () output
        if branch_pred is None:
            unit = self.graph.add_make_tuple([], parent=bb).out_port(0)
            branch_pred = self.graph.add_tag(variants=[TupleType([])], tag=0, inp=unit, parent=bb).out_port(0)
        if variables is not None:
            self._add_output(variables, bb, [branch_pred])
        else:
            assert outputs is not None
            self.graph.add_output(inputs=[branch_pred] + outputs, parent=bb)


class ExpressionCompiler(CompilerBase, AstVisitor):
    """ A compiler from Python expressions to Hugr. """
    variables: VarMap
    global_variables: VarMap

    def __init__(self, graph: Hugr):
        self.graph = graph
        self.variables = {}
        self.global_variables = {}

    def compile(self, expr: ast.expr, variables: VarMap, parent: Node, global_variables: VarMap, **_kwargs: Any) \
            -> OutPort:
        """ Compiles an expression and returns a single port holding the output value. """
        self.variables = variables
        self.global_variables = global_variables
        with self.graph.parent(parent):
            res = self.visit(expr)
        return res

    def compile_row(self, expr: ast.expr, variables: VarMap, parent: Node, global_variables: VarMap, **kwargs: Any) \
            -> list[OutPort]:
        """ Compiles a row expression and returns a list of ports, one for
        each value in the row.

        On Python-level, we treat tuples like rows on top-level. However,
        nested tuples are treated like regular Guppy tuples.
        """
        # Top-level tuple is turned into row
        if isinstance(expr, ast.Tuple):
            return [self.compile(e, variables, parent, global_variables, **kwargs) for e in expr.elts]
        else:
            return [self.compile(expr, variables, parent, global_variables)]

    def visit(self, node: ast.expr, *args: Any, **kwargs: Any) -> OutPort:
        # Overload visitor method restricting type to expressions
        return super().visit(node, *args, **kwargs)  # type: ignore

    def visit_Constant(self, node: ast.Constant) -> OutPort:
        if type_from_python_value(node.value) is None:
            raise GuppyError("Unsupported constant expression", node)
        return self.graph.add_constant(node.value).out_port(0)

    def visit_Name(self, node: ast.Name) -> OutPort:
        x = node.id
        if x in self.variables or x in self.global_variables:
            var = self.variables[x] or self.global_variables[x]
            if len(var.errors_on_usage) > 0:
                # TODO: Report all errors?
                err = var.errors_on_usage[0]
                err.location = node
                raise err
            return var.port
        raise GuppyError(f"Variable `{x}` is not defined", node)

    def visit_JoinedString(self, node: ast.JoinedStr) -> OutPort:
        raise GuppyError("Guppy does not support formatted strings", node)

    def visit_Tuple(self, node: ast.Tuple) -> OutPort:
        return self.graph.add_make_tuple(inputs=[self.visit(e) for e in node.elts]).out_port(0)

    def visit_List(self, node: ast.List) -> OutPort:
        raise NotImplementedError()

    def visit_Set(self, node: ast.Set) -> OutPort:
        raise NotImplementedError()

    def visit_Dict(self, node: ast.Dict) -> OutPort:
        raise NotImplementedError()

    def visit_UnaryOp(self, node: ast.UnaryOp) -> OutPort:
        port = self.visit(node.operand)
        ty = port.ty
        if isinstance(node.op, ast.UAdd):
            assert_arith_type(ty, node.operand)
            return port  # Unary plus is a noop
        elif isinstance(node.op, ast.USub):
            assert_arith_type(ty, node.operand)
            func = "ineg" if isinstance(ty, IntType) else "fneg"
            return self.graph.add_arith(func, args=[port], out_ty=ty).out_port(0)
        elif isinstance(node.op, ast.Not):
            assert_bool_type(ty, node.operand)
            return self.graph.add_arith("not", args=[port], out_ty=ty).out_port(0)
        elif isinstance(node.op, ast.Invert):
            # The unary invert operator `~` is defined as `~x = -(x + 1)` and only valid for integer
            # types. See https://docs.python.org/3/reference/expressions.html#unary-arithmetic-and-bitwise-operations
            # TODO: Do we want to follow the Python definition or have a custom HUGR op?
            assert_int_type(ty, node.operand)
            one = self.graph.add_constant(0)
            inc = self.graph.add_arith("iadd", args=[port, one.out_port(0)], out_ty=ty)
            inv = self.graph.add_arith("ineg", args=[inc.out_port(0)], out_ty=ty)
            return inv.out_port(0)
        else:
            raise InternalGuppyError(f"Unexpected unary operator encountered: {node.op}")

    def binary_arith_op(self, left: OutPort, left_expr: ast.expr, right: OutPort, right_expr: ast.expr,
                        int_func: str, float_func: str, bool_out: bool) -> OutPort:
        """ Helper function for compiling binary arithmetic operations. """
        assert_arith_type(left.ty, left_expr)
        assert_arith_type(right.ty, right_expr)
        # Automatic coercion from `int` to `float` if one of the operands is `float`
        is_float = isinstance(left.ty, FloatType) or isinstance(right.ty, FloatType)
        if is_float:
            if isinstance(left.ty, IntType):
                left = self.graph.add_arith("int_to_float", args=[left], out_ty=FloatType()).out_port(0)
            if isinstance(right.ty, IntType):
                right = self.graph.add_arith("int_to_float", args=[right], out_ty=IntType()).out_port(0)
        return_ty = BoolType() if bool_out else left.ty  # At this point we have `left.ty == right.ty`
        node = self.graph.add_arith(float_func if is_float else int_func, args=[left, right], out_ty=return_ty)
        return node.out_port(0)

    def visit_BinOp(self, node: ast.BinOp) -> OutPort:
        left = self.visit(node.left)
        right = self.visit(node.right)
        if isinstance(node.op, ast.Add):
            return self.binary_arith_op(left, node.left, right, node.right, "iadd", "fadd", False)
        elif isinstance(node.op, ast.Sub):
            return self.binary_arith_op(left, node.left, right, node.right, "isub", "fsub", False)
        elif isinstance(node.op, ast.Mult):
            return self.binary_arith_op(left, node.left, right, node.right, "imul", "fmul", False)
        elif isinstance(node.op, ast.Div):
            return self.binary_arith_op(left, node.left, right, node.right, "idiv", "fdiv", False)
        elif isinstance(node.op, ast.Mod):
            return self.binary_arith_op(left, node.left, right, node.right, "imod", "fmod", False)
        elif isinstance(node.op, ast.Pow):
            return self.binary_arith_op(left, node.left, right, node.right, "ipow", "fpow", False)
        else:
            raise GuppyError(f"Binary operator `{node.op}` is not supported", node.op)

    def visit_Compare(self, node: ast.Compare) -> OutPort:
        # Support chained comparisons, e.g. `x <= 5 < y` by compiling to `and(x <= 5, 5 < y)`
        left_expr = node.left
        left = self.visit(left_expr)
        acc = None
        for right_expr, op in zip(node.comparators, node.ops):
            right = self.visit(right_expr)
            if isinstance(op, ast.Eq) or isinstance(op, ast.Is):
                # TODO: How is equality defined? What can the operators be?
                res = self.graph.add_arith("eq", args=[left, right], out_ty=BoolType()).out_port(0)
            elif isinstance(op, ast.NotEq) or isinstance(op, ast.IsNot):
                res = self.graph.add_arith("neq", args=[left, right], out_ty=BoolType()).out_port(0)
            elif isinstance(op, ast.Lt):
                res = self.binary_arith_op(left, left_expr, right, right_expr, "ilt", "flt", True)
            elif isinstance(op, ast.LtE):
                res = self.binary_arith_op(left, left_expr, right, right_expr, "ileq", "fleq", True)
            elif isinstance(op, ast.Gt):
                res = self.binary_arith_op(left, left_expr, right, right_expr, "igt", "fgt", True)
            elif isinstance(op, ast.GtE):
                res = self.binary_arith_op(left, left_expr, right, right_expr, "igeg", "fgeg", True)
            else:
                # Remaining cases are `in`, and `not in`.
                # TODO: We want to support this once collections are added
                raise GuppyError(f"Binary operator `{ast.unparse(op)}` is not supported", op)
            left = right
            left_expr = right_expr
            if acc is None:
                acc = res
            else:
                acc = self.graph.add_arith("and", args=[acc, res], out_ty=BoolType()).out_port(0)
        return acc

    def visit_BoolOp(self, node: ast.BoolOp) -> OutPort:
        if isinstance(node.op, ast.And):
            func = "and"
        elif isinstance(node.op, ast.Or):
            func = "or"
        else:
            raise InternalGuppyError(f"Unexpected BoolOp encountered: {node.op}")
        operands = [self.visit(operand) for operand in node.values]
        acc = operands[0]
        for operand in operands[1:]:
            acc = self.graph.add_arith(func, args=[acc, operand], out_ty=BoolType()).out_port(0)
        return acc

    def visit_Call(self, node: ast.Call) -> OutPort:
        # We need to figure out if this is a direct or indirect call
        f = node.func
        if isinstance(f, ast.Name) and f.id in self.global_variables and f.id not in self.variables:
            is_direct = True
            var = self.global_variables[f.id]
            func_port = var.port
        else:
            is_direct = False
            func_port = self.visit(f)

        func_ty = func_port.ty
        if not isinstance(func_ty, FunctionType):
            raise GuppyTypeError(f"Expected function type, got `{func_ty}`", f)
        if len(node.keywords) > 0:
            # TODO: Implement this
            raise GuppyError(f"Argument passing by keyword is not supported", node.keywords[0])
        exp, act = len(func_ty.args), len(node.args)
        if exp < act:
            raise GuppyError(f"Not enough arguments passed (expected {exp}, got {act})", node)
        if act < exp:
            raise GuppyError(f"Unexpected argument", node.args[-1])

        args = []
        for i, arg in enumerate(node.args):
            port = self.visit(arg)
            if port.ty != func_ty.args[i]:
                raise GuppyTypeError(f"Expected argument of type `{func_ty.args[i]}`, got `ty`", arg)
            args.append(port)

        if is_direct:
            call = self.graph.add_call(func_port, args)
        else:
            call = self.graph.add_indirect_call(func_port, args)

        # Group outputs into tuple
        returns = [call.out_port(i) for i in range(len(func_ty.returns))]
        if len(returns) > 1:
            return self.graph.add_make_tuple(inputs=returns).out_port(0)
        return returns[0]


# Types for control-flow hooks needed for statement compilation
LoopHook = Callable[[BBNode, VarMap], Optional[BBNode]]
ReturnHook = Callable[[BBNode, ast.Return, list[OutPort]], Optional[BBNode]]


class StatementCompiler(CompilerBase, AstVisitor):
    """ A compiler from Python statements to Hugr. """
    line_offset: int
    expr_compiler: ExpressionCompiler
    functional_stmt_compiler: "FunctionalStatementCompiler"

    def __init__(self, graph: Hugr, line_offset: int):
        self.graph = graph
        self.line_offset = line_offset
        self.expr_compiler = ExpressionCompiler(graph)

    def compile_list(self, nodes: list[ast.stmt], variables: VarMap, bb: BBNode, global_variables: VarMap,
                     return_hook: ReturnHook, continue_hook: Optional[LoopHook] = None,
                     break_hook: Optional[LoopHook] = None) -> Optional[BBNode]:
        """ Compiles a list of statements into a basic block given
        a map of all active variables.

        Returns the basic block in which compilation can be resumed afterward.
        Or, returns `None` if all control-flow paths do a jump (i.e. `return`,
        `break` or `continue`.
        """
        next_functional = False
        for node in nodes:
            if bb is None:
                raise GuppyError("Unreachable code", node)
            if is_functional_annotation(node):
                next_functional = True
                continue

            if next_functional:
                bb = self.functional_stmt_compiler.visit(node, variables, bb, global_variables=global_variables,
                                                         return_hook=return_hook, continue_hook=continue_hook,
                                                         break_hook=break_hook)
                next_functional = False
            else:
                bb = self.visit(node, variables, bb, global_variables=global_variables, return_hook=return_hook,
                                continue_hook=continue_hook, break_hook=break_hook)
        return bb

    def visit_Assign(self, node: ast.Assign, variables: VarMap, bb: BBNode, **kwargs) -> Optional[BBNode]:
        if len(node.targets) > 1:
            # This is the case for assignments like `a = b = 1`
            raise GuppyError("Multi assignment not supported", node)
        target = node.targets[0]
        loc = {SourceLoc.from_ast(node, self.line_offset)}
        row = self.expr_compiler.compile_row(node.value, variables, bb, **kwargs)
        assert len(row) > 0

        # Easiest case is if the LHS is a single variable
        if isinstance(target, ast.Name):
            if len(row) == 1:
                port = row[0]
                variables[target.id] = Variable(target.id, port, loc)
            else:
                # Pack row into tuple
                port = self.graph.add_make_tuple(inputs=row, parent=bb).out_port(0)
                variables[target.id] = Variable(target.id, port, loc)
            return bb

        # Otherwise, the LHS is a (potentially nested) tuple pattern which might
        # require unpacking
        if not isinstance(target, ast.Tuple):
            raise InternalGuppyError(f"Unexpected node on LHS of assign: {node}")
        if len(row) == 1:
            # If the row only contains a single element, put it on the unpack stack
            to_unpack: deque[tuple[ast.expr, OutPort]] = deque([(target, row[0])])
        else:
            # Otherwise, the number of row elements must match with the pattern and
            # each element is put separately on the unpack stack
            n, m = len(target.elts), len(row)
            if n != m:
                raise GuppyTypeError(f"{'Too many' if n < m else 'Not enough'} "
                                     f"values to unpack (expected {n}, got {m})", node)
            to_unpack = deque(zip(target.elts, row))

        names = set()
        while len(to_unpack) > 0:
            pattern, port = to_unpack.popleft()
            if isinstance(pattern, ast.Name):
                name = pattern.id
                if name in names:
                    # Python actually allows statements like `x, x = 1, 2` with `x` being
                    # bound to `2` afterward. It would be easy to implement this behaviour
                    # here, but do we want that?
                    # TODO: Decide whether we allow this or not
                    raise GuppyError(f"Variable {name} already occurred in this pattern", pattern)
                names.add(name)
                variables[name] = Variable(name, port, loc)
            elif isinstance(pattern, ast.Tuple):
                ty = port.ty
                if not isinstance(ty, TupleType):
                    raise GuppyTypeError(f"Expected tuple type to unpack, but got `{ty}`", node.value)
                n, m = len(pattern.elts), len(ty.element_types)
                if n != m:
                    raise GuppyTypeError(f"{'Too many' if n < m else 'Not enough'} "
                                         f"values to unpack (expected {n}, got {m})", node)
                unpack = self.graph.add_unpack_tuple(input_tuple=port, parent=bb)
                for i, el_pat in enumerate(pattern.elts):
                    to_unpack.append((el_pat, unpack.out_port(i)))
        return bb

    def visit_AnnAssign(self, node: ast.AnnAssign, variables: VarMap, bb: BBNode, **kwargs) -> Optional[BBNode]:
        # TODO: Figure out what to do with type annotations
        raise NotImplementedError()

    def visit_AugAssign(self, node: ast.AugAssign, variables: VarMap, bb: BBNode, **kwargs) -> Optional[BBNode]:
        # TODO: Set all source location attributes
        bin_op = ast.BinOp(left=node.target, op=node.op, right=node.value)
        assign = ast.Assign(targets=[node.target], value=bin_op, lineno=node.lineno, col_offset=node.col_offset)
        return self.visit_Assign(assign, variables, bb, **kwargs)

    def visit_Return(self, node: ast.Return, variables: VarMap, bb: BBNode, return_hook: ReturnHook,
                     **kwargs) -> Optional[BBNode]:
        return return_hook(bb, node, self.expr_compiler.compile_row(node.value, variables, bb, **kwargs))

    def visit_If(self, node: ast.If, variables: VarMap, bb: BBNode, **kwargs) -> Optional[BBNode]:
        # Finish the current basic block by putting the if condition at the end
        cond_port = self.expr_compiler.compile(node.test, variables, bb, **kwargs)
        assert_bool_type(cond_port.ty, node.test)
        self._finish_bb(bb, variables, branch_pred=cond_port)
        # Compile statements in the `if` branch
        if_bb, if_vars = self._make_bb(bb, variables)
        if_bb = self.compile_list(node.body, if_vars, if_bb, **kwargs)
        # Compile statements in the `else` branch
        else_exists = len(node.orelse) > 0
        if else_exists:
            # TODO: The logic later would be easier if we always create an else BB, even
            #  if else_exists = False
            else_bb, else_vars = self._make_bb(bb, variables)
            else_bb = self.compile_list(node.orelse, else_vars, else_bb, **kwargs)
        else:  # If we don't have an `else` branch, just use the initial BB
            else_bb = bb
            else_vars = variables.copy()

        # We need to handle different cases depending on whether branches jump (i.e. return, continue, or break)
        if if_bb is None and else_bb is None:
            # Both jump: This means the whole if-statement jumps, so we don't have to do anything
            return None
        elif if_bb is None:
            # If branch jumps: If else branch exists, we can continue in its BB. Otherwise,
            # we have to create a new BB
            if not else_exists:
                else_bb, else_vars = self._make_bb(bb, variables)
            for var in else_vars.values():
                variables[var.name] = var
            return else_bb
        elif else_bb is None:
            # Else branch jumps: We continue in the BB of the if branch
            for var in if_vars.values():
                variables[var.name] = var
            return if_bb
        else:
            # No branch jumps: We have to merge the control flow
            # Input of the merge BB will be all variables that are defined in both
            # the `if` and `else` branch
            merge_bb = self.graph.add_block(bb.parent)
            merge_input = self.graph.add_input(output_tys=[], parent=merge_bb)
            self.graph.add_edge(if_bb.add_out_port(None), merge_bb.add_in_port(None))
            self.graph.add_edge(else_bb.add_out_port(None), merge_bb.add_in_port(None))
            if_outputs: list[OutPort] = []
            else_outputs: list[OutPort] = []
            for name in set(if_vars.keys()) | set(else_vars.keys()):
                if name in if_vars and name in else_vars:
                    if_var, else_var = if_vars[name], else_vars[name]
                    variables[name] = merge_variables(if_var, else_var, new_port=merge_input.add_out_port(if_var.ty))
                    if_outputs.append(if_var.port)
                    if else_exists:
                        else_outputs.append(else_var.port)
                else:
                    var = if_vars[name] if name in if_vars else else_vars[name]
                    err = GuppyError(f"Variable `{name}` only defined in `{'if' if name in if_vars else 'else'}` branch")
                    variables[name] = Variable(name, UndefinedPort(var.ty), var.defined_at, [err])
            self._finish_bb(if_bb, outputs=if_outputs)
            if else_exists:
                self._finish_bb(else_bb, outputs=else_outputs)
            return merge_bb

    def visit_While(self, node: ast.While, variables: VarMap, bb: BBNode, **kwargs) -> Optional[BBNode]:
        # Finish the current basic block
        self._finish_bb(bb, variables)
        # Add basic blocks for loop head, loop body, and loop tail
        head_bb, head_vars = self._make_bb(bb, variables)
        body_bb, body_vars = self._make_bb(head_bb, variables)  # Body must be first successor of head
        tail_bb, tail_vars = self._make_bb(head_bb, variables)
        # Insert loop condition into the head
        cond_port = self.expr_compiler.compile(node.test, head_vars, head_bb, **kwargs)
        assert_bool_type(cond_port.ty, node.test)
        self._finish_bb(head_bb, head_vars, branch_pred=cond_port)

        # Define hook that is executed on `continue` and `break`
        def jump_hook(target_bb: BBNode, curr_bb: BBNode, curr_vars: VarMap) -> Optional[BBNode]:
            # Ignore new variables that are only defined in the loop
            self._finish_bb(curr_bb, {name: curr_vars[name] for name in curr_vars if name in variables})
            self.graph.add_edge(curr_bb.add_out_port(None), target_bb.add_in_port(None))
            for curr_var in curr_vars.values():
                name = curr_var.name
                if name in variables:
                    orig_var = variables[name]
                    variables[name] = merge_variables(curr_var, orig_var, new_port=tail_vars[name].port)
                else:
                    err = GuppyError(f"Variable `{name}` only defined inside of loop body")
                    variables[name] = Variable(name, UndefinedPort(curr_var.ty), curr_var.defined_at, [err])
            return None

        # Compile loop body
        kwargs.pop("continue_hook")
        kwargs.pop("break_hook")
        body_bb = self.compile_list(node.body, body_vars, body_bb,
                                    continue_hook=lambda curr_bb, curr_vars: jump_hook(head_bb, curr_bb, curr_vars),
                                    break_hook=lambda curr_bb, curr_vars: jump_hook(tail_bb, curr_bb, curr_vars),
                                    **kwargs)

        if body_bb is None:
            # This happens if the loop body always returns. We continue with tail_bb
            # nonetheless since the loop condition could be false for the first iteration,
            # so it's not a guaranteed return
            return tail_bb

        # Otherwise, jump back to the head. We also have to check that the variables used
        # in the head haven't collected errors_on_usage
        jump_hook(head_bb, body_bb, body_vars)
        for name_node in name_nodes_in_expr(node.test):
            errs = variables[name_node.id].errors_on_usage
            if len(errs) > 0:
                # TODO: Show all errors?
                err = errs[0]
                if err.location is None:
                    err.location = name_node
                raise err

        # Continue compilation in the tail
        return tail_bb

    def visit_Continue(self, node: ast.Continue, variables: VarMap, bb: BBNode, continue_hook: Optional[LoopHook],
                       **kwargs) -> Optional[BBNode]:
        if not continue_hook:
            # The Python parser ensures that `continue` can only occur inside of loops.
            # If `continue_bb` is not defined, this means that the `continue` must refer
            # to some outer loop (either in nested graph or outer Python)
            raise GuppyError("Cannot continue external loop inside of Guppy function", node)
        return continue_hook(bb, variables)

    def visit_Break(self, node: ast.Break, variables: VarMap, bb: BBNode, break_hook: Optional[LoopHook],
                    **kwargs) -> Optional[BBNode]:
        if not break_hook:
            # The Python parser ensures that `break` can only occur inside of loops.
            # If `break_bb` is not defined, this means that the `break` must refer
            # to some outer loop (either in nested graph or outer Python)
            raise GuppyError("Cannot break external loop inside of Guppy function", node)
        return break_hook(bb, variables)


class FunctionalStatementCompiler(StatementCompiler):
    """ A compiler from Python statements to Hugr only using functional control-flow nodes. """
    def visit_Break(self, node: ast.Break, *args, **kwargs) -> BBNode:
        raise GuppyError("Break is not allowed in a functional statement", node)

    def visit_Continue(self, node: ast.Continue, *args, **kwargs) -> BBNode:
        raise GuppyError("Continue is not allowed in a functional statement", node)

    def visit_Return(self, node: ast.Return, *args, **kwargs) -> BBNode:
        raise GuppyError("Return is not allowed in a functional statement", node)

    def visit_If(self, node: ast.If, variables: VarMap, bb: BBNode, **kwargs) -> BBNode:
        cond_port = self.expr_compiler.compile(node.test, variables, bb, **kwargs)
        assert_bool_type(cond_port.ty, node.test)
        vs = list(sorted(variables.values(), key=lambda v: v.name))
        conditional = self.graph.add_conditional(cond_input=cond_port, inputs=[v.port for v in vs], parent=bb)

        if_dfg, if_vars = self._make_case(variables, conditional)
        else_dfg, else_vars = self._make_case(variables, conditional)
        self.compile_list(node.body, if_vars, if_dfg, **kwargs)
        self.compile_list(node.orelse, else_vars, else_dfg, **kwargs)

        if_output = self.graph.add_output(parent=if_dfg)
        else_output = self.graph.add_output(parent=else_dfg)
        for name in set(if_vars.keys()) | set(else_vars.keys()):
            if name in if_vars and name in else_vars:
                if_var, else_var = if_vars[name], else_vars[name]
                variables[name] = merge_variables(if_var, else_var, new_port=conditional.add_out_port(if_var.ty))
                self.graph.add_edge(if_var.port, if_output.add_in_port(if_var.ty))
                self.graph.add_edge(else_var.port, else_output.add_in_port(else_var.ty))
            else:
                var = if_vars[name] if name in if_vars else else_vars[name]
                err = GuppyError(f"Variable `{name}` only defined in `{'if' if name in if_vars else 'else'}` branch")
                variables[name] = Variable(name, UndefinedPort(var.ty), var.defined_at, [err])
        return bb

    def visit_While(self, node: ast.While, variables: VarMap, bb: BBNode, **kwargs) -> BBNode:
        # TODO: Once we have explicit variable tracking for nested functions, we can remove the
        #  variable sorting in the code below
        # Turn into tail controlled loop by enclosing into initial if statement
        cond_port = self.expr_compiler.compile(node.test, variables, bb, **kwargs)
        assert_bool_type(cond_port.ty, node.test)
        conditional = self.graph.add_conditional(cond_input=cond_port, parent=bb,
                                                 inputs=[v.port for v in sorted(variables.values(), key=lambda v: v.name)])
        start_dfg, start_vars = self._make_case(variables, conditional)
        skip_dfg, skip_vars = self._make_case(variables, conditional)
        # The skip block is just an identity DFG
        self.graph.add_output(inputs=[v.port for v in sorted(skip_vars.values(), key=lambda v: v.name)],
                              parent=skip_dfg)

        # Now compile loop body itself as TailLoop node
        loop = self.graph.add_tail_loop(inputs=[v.port for v in sorted(start_vars.values(), key=lambda v: v.name)],
                                        parent=start_dfg)
        loop_vars = self._add_input(variables, loop)
        self.compile_list(node.body, loop_vars, loop, **kwargs)
        loop_output = self.graph.add_output(input_tys=[BoolType()],  # Reserve condition port
                                            parent=loop)
        start_dfg_output = self.graph.add_output(parent=start_dfg)
        for var in sorted(loop_vars.values(), key=lambda v: v.name):
            name = var.name
            if name in variables:
                orig_var = variables[name]
                variables[name] = merge_variables(var, orig_var, new_port=conditional.add_out_port(var.ty))
                self.graph.add_edge(var.port, loop_output.add_in_port(var.ty))
                self.graph.add_edge(loop.add_out_port(var.ty), start_dfg_output.add_in_port(var.ty))
            else:
                err = GuppyError(f"Variable `{name}` only defined in loop body")
                variables[name] = Variable(name, UndefinedPort(var.ty), var.defined_at, [err])

        # Insert loop condition. We have to check first that the variables used in
        # the loop condition haven't collected errors_on_usage
        for name_node in name_nodes_in_expr(node.test):
            errs = variables[name_node.id].errors_on_usage
            if len(errs) > 0:
                # TODO: Show all errors?
                err = errs[0]
                if err.location is None:
                    err.location = name_node
                raise err
        cond_port = self.expr_compiler.compile(node.test, loop_vars, loop, **kwargs)
        assert isinstance(cond_port.ty, BoolType)  # We already ensured this for the initial if
        self.graph.add_edge(cond_port, loop_output.in_port(0))
        return bb


@dataclass()
class GuppyFunction:
    """ Class holding all information associated with a Function during compilation. """
    name: str
    module: "GuppyModule"
    def_node: Node
    ty: FunctionType
    ast: ast.FunctionDef

    def __call__(self, *args, **kwargs):
        # The `@guppy` annotator returns a `GuppyFunction`. If the user
        # tries to call it, we can give a nice error message:
        raise GuppyError("Guppy functions can only be called inside of Guppy functions")


class FunctionCompiler(CompilerBase):
    """ A compiler from Python function definitions to Hugr functions. """
    stmt_compiler: StatementCompiler
    line_offset: int

    def __init__(self, graph: Hugr):
        self.graph = graph
        stmt_compiler = StatementCompiler(graph, 0)
        stmt_compiler.functional_stmt_compiler = FunctionalStatementCompiler(graph, 0)
        stmt_compiler.functional_stmt_compiler.functional_stmt_compiler = stmt_compiler.functional_stmt_compiler
        self.stmt_compiler = stmt_compiler

    @staticmethod
    def validate_signature(func_def: ast.FunctionDef) -> FunctionType:
        """ Checks the signature of a function definition and returns the
        corresponding Guppy type. """
        if len(func_def.args.posonlyargs) != 0:
            raise GuppyError("Positional-only parameters not supported", func_def.args.posonlyargs[0])
        if len(func_def.args.kwonlyargs) != 0:
            raise GuppyError("Keyword-only parameters not supported", func_def.args.kwonlyargs[0])
        if func_def.args.vararg is not None:
            raise GuppyError("*args not supported", func_def.args.vararg)
        if func_def.args.kwarg is not None:
            raise GuppyError("**kwargs not supported", func_def.args.kwarg)
        if func_def.returns is None:
            raise GuppyError("Return type must be annotated", func_def)

        arg_tys = []
        arg_names = []
        for i, arg in enumerate(func_def.args.args):
            if arg.annotation is None:
                raise GuppyError("Argument type must be annotated", arg)
            ty = type_from_ast(arg.annotation)
            arg_tys.append(ty)
            arg_names.append(arg.arg)

        ret_type = type_from_ast(func_def.returns)
        if isinstance(ret_type, TupleType):
            ret_tys = ret_type.element_types
        elif isinstance(ret_type, RowType):
            ret_tys = ret_type.element_types
        else:
            ret_tys = [ret_type]

        return FunctionType(arg_tys, ret_tys, arg_names)

    def compile(self, module: "GuppyModule", func_def: ast.FunctionDef, def_node: Optional[Node],
                global_variables: VarMap, line_offset: int) -> GuppyFunction:
        """ Compiles a `FunctionDef` AST node into a Guppy function. """
        self.line_offset = line_offset
        self.stmt_compiler.line_offset = line_offset

        func_ty = self.validate_signature(func_def)
        args = func_def.args.args

        def_input = self.graph.add_input(parent=def_node)
        cfg = self.graph.add_cfg(def_node, inputs=[def_input.add_out_port(ty) for ty in func_ty.args])
        input_bb = self.graph.add_block(cfg)
        input_node = self.graph.add_input(output_tys=func_ty.args, parent=input_bb)

        variables: VarMap = {}
        for i, arg in enumerate(args):
            name = arg.arg
            port = input_node.out_port(i)
            variables[name] = Variable(name, port, {SourceLoc.from_ast(arg, self.line_offset)}, [])

        return_block = self.graph.add_exit(output_tys=func_ty.returns, parent=cfg)
        return_port = return_block.add_in_port(None)

        # Define hook that is executed on return
        def return_hook(curr_bb: BBNode, node: ast.Return, row: list[OutPort]) -> Optional[BBNode]:
            tys = [p.ty for p in row]
            if tys != func_ty.returns:
                raise GuppyTypeError(f"Return type mismatch: expected `{RowType(func_ty.returns)}`, "
                                     f"got `{RowType(tys)}`", node.value)
            self.stmt_compiler._finish_bb(curr_bb, outputs=row)
            self.graph.add_edge(curr_bb.add_out_port(None), return_port)
            return None

        # Compile function body
        final_bb = self.stmt_compiler.compile_list(func_def.body, variables, input_bb, global_variables, return_hook)

        # If we're still in a basic block after compiling the whole body,
        # we have to add an implicit void return
        if final_bb is not None:
            if len(func_ty.returns) > 0:
                raise GuppyError(f"Expected return statement of type `{RowType(func_ty.returns)}`", func_def.body[-1])
            self.stmt_compiler._finish_bb(final_bb, outputs=[])
            self.graph.add_edge(final_bb.add_out_port(None), return_port)

        # Add final output node for the def block
        self.graph.add_output(inputs=[cfg.add_out_port(ty) for ty in func_ty.returns], parent=def_node)

        return GuppyFunction(func_def.name, module, def_node, func_ty, func_def)


def format_source_location(source_lines: list[str], loc: Union[ast.AST, ast.operator, ast.expr, ast.arg, ast.Name],
                           line_offset: int, num_lines: int = 3, indent: int = 4) -> str:
    """ Creates a pretty banner to show source locations for errors. """
    s = "".join(source_lines[max(loc.lineno-num_lines, 0):loc.lineno]).rstrip()
    s += "\n" + loc.col_offset * " " + (loc.end_col_offset - loc.col_offset) * "^"
    s = textwrap.dedent(s).splitlines()
    # Add line numbers
    line_numbers = [str(line_offset + loc.lineno - i) + ":" for i in range(num_lines, 0, -1)]
    longest = max(len(ln) for ln in line_numbers)
    prefixes = [ln + " " * (longest - len(ln) + indent) for ln in line_numbers]
    res = ""
    for prefix, line in zip(prefixes, s[:-1]):
        res += prefix + line + "\n"
    res += (longest + indent) * " " + s[-1]
    return res


class GuppyModule(object):
    """ A Guppy module backed by a Hugr graph.

    Instances of this class can be used as a decorator to add functions
    to the module. After all functions are added, `compile()` must be
    called to obtain the Hugr.
    """
    name: str
    graph: Hugr
    module_node: Node
    compiler: FunctionCompiler
    annotated_funcs: dict[str, tuple[Callable, ast.FunctionDef, list[str], int]]  # function, AST, source lines, line offset
    fun_decls: list[GuppyFunction]

    def __init__(self, name: str):
        self.name = name
        self.graph = Hugr(name)
        self.module_node = self.graph.add_root("module")
        self.compiler = FunctionCompiler(self.graph)
        self.annotated_funcs = {}
        self.fun_decls = []

    def __call__(self, f):
        source_lines, line_offset = inspect.getsourcelines(f)
        line_offset -= 1
        source = "".join(source_lines)  # Lines already have trailing \n's

        func_ast = ast.parse(source).body[0]
        if not isinstance(func_ast, ast.FunctionDef):
            raise GuppyError("Only functions can be placed in modules", func_ast)
        if func_ast.name in self.annotated_funcs:
            raise GuppyError(f"Module `{self.name}` already contains a function named `{func_ast.name}` "
                             f"(declared at {SourceLoc.from_ast(self.annotated_funcs[func_ast.name][1], line_offset)})",
                             func_ast)
        self.annotated_funcs[func_ast.name] = f, func_ast, source_lines, line_offset
        return None

    def compile(self) -> Hugr:
        """ Compiles the module and returns the final Hugr. """
        try:
            global_variables = {}
            defs = {}
            for name, (f, func_ast, source_lines, line_offset) in self.annotated_funcs.items():
                func_ty = self.compiler.validate_signature(func_ast)
                def_node = self.graph.add_def(func_ty, self.module_node, func_ast.name)
                defs[name] = def_node
                loc = SourceLoc.from_ast(func_ast, line_offset)
                global_variables[name] = Variable(name, def_node.out_port(0), {loc}, [])
            for name, (f, func_ast, source_lines, line_offset) in self.annotated_funcs.items():
                func = self.compiler.compile(self, func_ast, defs[name], global_variables, line_offset)
                self.fun_decls.append(func)
            return self.graph
        except GuppyError as err:
            if err.location:
                loc = err.location
                line = line_offset + loc.lineno
                print(f'Guppy compilation failed. Error in file "{inspect.getsourcefile(f)}", '
                      f"line {line}, in {inspect.getmodule(f).__name__}\n", file=sys.stderr)
                print(format_source_location(source_lines, loc, line_offset+1), file=sys.stderr)
            else:
                print(f'Guppy compilation failed. Error in file "{inspect.getsourcefile(f)}"\n', file=sys.stderr)
            print(f"{err.__class__.__name__}: {err.msg}", file=sys.stderr)
            sys.exit(1)


def guppy(f) -> Hugr:
    """ Decorator to compile functions outside of modules for testing.

    Note that recursion without a module is not supported.
    """
    source_lines, line_offset = inspect.getsourcelines(f)
    source = "".join(source_lines)  # Lines already have trailing \n's
    graph = Hugr()
    func_ast = ast.parse(source).body[0]
    assert isinstance(func_ast, ast.FunctionDef)
    compiler = FunctionCompiler(graph)
    try:
        compiler.compile(GuppyModule(""), func_ast, None, {}, line_offset-1)
    except GuppyError as err:
        if err.location:
            loc = err.location
            line = line_offset + loc.lineno - 1
            print(f'Guppy compilation failed. Error in file "{inspect.getsourcefile(f)}", '
                  f"line {line}, in {inspect.getmodule(f).__name__}\n", file=sys.stderr)
            print(format_source_location(source_lines, loc, line_offset), file=sys.stderr)
        else:
            print(f'Guppy compilation failed. Error in file "{inspect.getsourcefile(f)}"\n', file=sys.stderr)
        print(f"{err.__class__.__name__}: {err.msg}", file=sys.stderr)
        # sys.exit(1)
    return graph
