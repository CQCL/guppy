import ast
import itertools
from dataclasses import dataclass, field
from typing import Optional, NamedTuple, Iterator, Any

from guppy.bb import BB, CompiledBB, VarRow
from guppy.compiler_base import return_var, VarMap
from guppy.error import InternalGuppyError, GuppyError
from guppy.ast_util import AstVisitor, name_nodes_in_ast, line_col, set_location
from guppy.guppy_types import GuppyType
from guppy.hugr.hugr import Node, Hugr


@dataclass
class CFG:
    """A control-flow graph."""

    bbs: list[BB] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.entry_bb = self.new_bb()
        self.exit_bb = self.new_bb()

    def new_bb(
        self,
        pred: Optional[BB] = None,
        preds: Optional[list[BB]] = None,
        statements: Optional[list[ast.stmt]] = None,
    ) -> BB:
        """Adds a new basic block to the CFG.

        Optionally, a single predecessor or a list of predecessor BBs can be passed.
        """
        preds = preds if preds is not None else [pred] if pred is not None else []
        bb = BB(len(self.bbs), predecessors=preds, statements=statements or [])
        self.bbs.append(bb)
        for p in preds:
            p.successors.append(bb)
        return bb

    def link(self, src_bb: BB, tgt_bb: BB) -> None:
        """Adds a control-flow edge between two basic blocks."""
        src_bb.successors.append(tgt_bb)
        tgt_bb.predecessors.append(src_bb)

    def _analyze_liveness(self) -> None:
        """Runs live variable analysis."""
        for bb in self.bbs:
            bb.vars.live_before = dict()
        self.exit_bb.vars.live_before = {
            x: self.exit_bb for x in self.exit_bb.vars.used
        }
        queue = set(self.bbs)
        while len(queue) > 0:
            bb = queue.pop()
            for pred in bb.predecessors:
                live_before = {x: pred for x in pred.vars.used} | {
                    x: b
                    for x, b in bb.vars.live_before.items()
                    if x not in pred.vars.assigned.keys()
                }
                if not set.issubset(
                    set(live_before.keys()), pred.vars.live_before.keys()
                ):
                    pred.vars.live_before |= live_before
                    queue.add(pred)

    def _analyze_definite_assignment(self) -> None:
        """Runs definite assignment analysis."""
        all_vars = set.union(
            *(bb.vars.used.keys() | bb.vars.assigned.keys() for bb in self.bbs)
        )
        for bb in self.bbs:
            bb.vars.assigned_before = all_vars.copy()
        self.entry_bb.vars.assigned_before = set()
        queue = set(self.bbs)
        while len(queue) > 0:
            bb = queue.pop()
            assigned_after = bb.vars.assigned_before | bb.vars.assigned.keys()
            for succ in bb.successors:
                if not set.issubset(succ.vars.assigned_before, assigned_after):
                    succ.vars.assigned_before &= assigned_after
                    queue.add(succ)

    def _analyze_maybe_assignment(self) -> None:
        """Runs maybe assignment analysis.

        This computes the variables that *might* be defined at every program point but
        are not guaranteed to be assigned. I.e. a variable that is defined on some paths
        but not on all paths.
        Note that this pass uses the results from the definite assignment analysis, so
        it must be run afterward.
        """
        for bb in self.bbs:
            bb.vars.maybe_assigned_before = set()
        queue = set(self.bbs)
        while len(queue) > 0:
            bb = queue.pop()
            maybe_ass_after = bb.vars.maybe_assigned_before | bb.vars.assigned.keys()
            for succ in bb.successors:
                maybe_ass = maybe_ass_after - succ.vars.assigned_before
                if not set.issubset(maybe_ass, succ.vars.maybe_assigned_before):
                    succ.vars.maybe_assigned_before |= maybe_ass
                    queue.add(succ)

    def analyze(self) -> None:
        """Runs all program analysis passes."""
        self._analyze_liveness()
        self._analyze_definite_assignment()
        self._analyze_maybe_assignment()

    def compile(
        self,
        graph: Hugr,
        input_row: VarRow,
        return_tys: list[GuppyType],
        parent: Node,
        global_variables: VarMap,
    ) -> None:
        """Compiles the CFG."""

        compiled: dict[BB, CompiledBB] = {}
        arg_names = [v.name for v in input_row]

        entry_compiled = self.entry_bb.compile(
            graph, input_row, return_tys, parent, global_variables
        )
        compiled[self.entry_bb] = entry_compiled

        # Visit all control-flow edges in BFS order
        stack = [
            (entry_compiled, entry_compiled.sig.output_rows[i], succ)
            # Put successors onto stack in reverse order to maintain the original order
            # when popping
            for i, succ in reversed(list(enumerate(self.entry_bb.successors)))
        ]
        while len(stack) > 0:
            pred, out_row, bb = stack.pop()

            # If the BB was already compiled, we just have to check that the signatures
            # match.
            if bb in compiled:
                assert len(out_row) == len(compiled[bb].sig.input_row)
                for v1, v2 in zip(out_row, compiled[bb].sig.input_row):
                    assert v1.name == v2.name
                    if v1.ty != v2.ty:
                        # Sort defined locations by line and column
                        d1 = sorted(v1.defined_at, key=line_col)
                        d2 = sorted(v2.defined_at, key=line_col)
                        [(v1, d1), (v2, d2)] = sorted(
                            [(v1, d1), (v2, d2)], key=lambda x: line_col(x[1][0])
                        )
                        f1 = [f"{{{i}}}" for i in range(len(d1))]
                        f2 = [f"{{{len(f1) + i}}}" for i in range(len(d2))]
                        raise GuppyError(
                            f"Variable `{v1.name}` can refer to different types: "
                            f"`{v1.ty}` (at {', '.join(f1)}) vs "
                            f"`{v2.ty}` (at {', '.join(f2)})",
                            bb.vars.live_before[v1.name].vars.used[v1.name],
                            d1 + d2,
                        )
                graph.add_edge(
                    pred.node.add_out_port(), compiled[bb].node.in_port(None)
                )

            # Otherwise, compile the BB and put successors on the stack
            else:
                # Live variables before the entry BB correspond to usages without prior
                # assignment
                for x, use_bb in self.entry_bb.vars.live_before.items():
                    # Functions arguments and global variables are fine
                    if x in arg_names or x in global_variables:
                        continue
                    # The rest results in an error. If the variable is defined on *some*
                    # paths, we can give a more informative error message
                    if x in use_bb.vars.maybe_assigned_before:
                        # TODO: Can we point to the actual path in the message in a nice
                        #  way?
                        raise GuppyError(
                            f"Variable `{x}` is not defined on all control-flow paths.",
                            use_bb.vars.used[x],
                        )
                    else:
                        raise GuppyError(
                            f"Variable `{x}` is not defined", use_bb.vars.used[x]
                        )

                bb_compiled = bb.compile(
                    graph, out_row, return_tys, parent, global_variables
                )
                graph.add_edge(pred.node.add_out_port(), bb_compiled.node.in_port(None))
                compiled[bb] = bb_compiled
                stack += [
                    (bb_compiled, bb_compiled.sig.output_rows[i], succ)
                    # Put successors onto stack in reverse order to maintain the
                    # original order when popping
                    for i, succ in reversed(list(enumerate(bb.successors)))
                ]


class Jumps(NamedTuple):
    """Holds jump targets for return, continue, and break during CFG construction."""

    return_bb: BB
    continue_bb: Optional[BB]
    break_bb: Optional[BB]


class CFGBuilder(AstVisitor[Optional[BB]]):
    """Constructs a CFG from ast nodes."""

    expr_builder: "ExprBuilder"
    cfg: CFG
    num_returns: int

    def __init__(self) -> None:
        self.expr_builder = ExprBuilder()

    def build(self, nodes: list[ast.stmt], num_returns: int) -> CFG:
        """Builds a CFG from a list of ast nodes.

        We also require the expected number of return ports for the whole CFG. This is
        needed to translate return statements into assignments of dummy return
        variables.
        """
        self.cfg = CFG()
        self.num_returns = num_returns

        final_bb = self.visit_stmts(
            nodes, self.cfg.entry_bb, Jumps(self.cfg.exit_bb, None, None)
        )

        # If we're still in a basic block after compiling the whole body, we have to add
        # an implicit void return
        if final_bb is not None:
            if num_returns > 0:
                raise GuppyError("Expected return statement", nodes[-1])
            self.cfg.link(final_bb, self.cfg.exit_bb)

        # In the main `BBCompiler`, we're going to turn return statements into
        # assignments of dummy variables `%ret_xxx`. To make the liveness analysis work,
        # we have to register those variables as being used in the exit BB
        self.cfg.exit_bb.vars.used = {return_var(i): None for i in range(num_returns)}  # type: ignore

        return self.cfg

    def visit_stmts(self, nodes: list[ast.stmt], bb: BB, jumps: Jumps) -> Optional[BB]:
        bb_opt: Optional[BB] = bb
        next_functional = False
        for node in nodes:
            if bb_opt is None:
                raise GuppyError("Unreachable code", node)
            if is_functional_annotation(node):
                next_functional = True
                continue

            if next_functional:
                # TODO: This should be an assertion that the Hugr can be un-flattened
                raise NotImplementedError()
                next_functional = False
            else:
                bb_opt = self.visit(node, bb_opt, jumps)
        return bb_opt

    def visit_Assign(self, node: ast.Assign, bb: BB, jumps: Jumps) -> Optional[BB]:
        node.value, bb = self.expr_builder.build(node.value, self.cfg, bb)
        bb.statements.append(node)
        bb.vars.update_used(node.value)
        for t in node.targets:
            for name in name_nodes_in_ast(t):
                bb.vars.assigned[name.id] = node
        return bb

    def visit_AugAssign(
        self, node: ast.AugAssign, bb: BB, jumps: Jumps
    ) -> Optional[BB]:
        bb.statements.append(node)
        bb.vars.update_used(node.value)
        bb.vars.update_used(node.target)  # The target is also used
        for name in name_nodes_in_ast(node.target):
            bb.vars.assigned[name.id] = node
        return bb

    def visit_Expr(self, node: ast.Expr, bb: BB, jumps: Jumps) -> Optional[BB]:
        _, bb = self.expr_builder.build(node.value, self.cfg, bb)
        return bb

    def visit_If(self, node: ast.If, bb: BB, jumps: Jumps) -> Optional[BB]:
        if_bb, else_bb = self.cfg.new_bb(), self.cfg.new_bb()
        self.expr_builder.build_branch(node.test, self.cfg, bb, if_bb, else_bb)
        if_bb = self.visit_stmts(node.body, if_bb, jumps)
        else_bb = self.visit_stmts(node.orelse, else_bb, jumps)
        # We need to handle different cases depending on whether branches jump (i.e.
        # return, continue, or break)
        if if_bb is None and else_bb is None:
            # Both jump: This means the whole if-statement jumps, so we don't have to do
            # anything
            return None
        elif if_bb is None:
            # If branch jumps: We continue in the BB of the else branch
            return else_bb
        elif else_bb is None:
            # Else branch jumps: We continue in the BB of the if branch
            return if_bb
        else:
            # No branch jumps: We have to merge the control flow
            return self.cfg.new_bb(preds=[if_bb, else_bb])

    def visit_While(self, node: ast.While, bb: BB, jumps: Jumps) -> Optional[BB]:
        head_bb = self.cfg.new_bb(pred=bb)
        body_bb, tail_bb = self.cfg.new_bb(), self.cfg.new_bb()
        self.expr_builder.build_branch(node.test, self.cfg, head_bb, body_bb, tail_bb)

        new_jumps = Jumps(
            return_bb=jumps.return_bb, continue_bb=head_bb, break_bb=tail_bb
        )
        body_bb = self.visit_stmts(node.body, body_bb, new_jumps)

        if body_bb is None:
            # This happens if the loop body always returns. We continue with tail_bb
            # nonetheless since the loop condition could be false for the first
            # iteration, so it's not a guaranteed return
            return tail_bb

        # Otherwise, jump back to the head and continue compilation in the tail.
        self.cfg.link(body_bb, head_bb)
        return tail_bb

    def visit_Continue(self, node: ast.Continue, bb: BB, jumps: Jumps) -> Optional[BB]:
        if not jumps.continue_bb:
            raise InternalGuppyError("Continue BB not defined")
        self.cfg.link(bb, jumps.continue_bb)
        return None

    def visit_Break(self, node: ast.Break, bb: BB, jumps: Jumps) -> Optional[BB]:
        if not jumps.break_bb:
            raise InternalGuppyError("Break BB not defined")
        self.cfg.link(bb, jumps.break_bb)
        return None

    def visit_Return(self, node: ast.Return, bb: BB, jumps: Jumps) -> Optional[BB]:
        if node.value is not None:
            node.value, bb = self.expr_builder.build(node.value, self.cfg, bb)
            bb.vars.update_used(node.value)
        self.cfg.link(bb, jumps.return_bb)
        # In the main `BBCompiler`, we're going to turn return statements into
        # assignments of dummy variables `%ret_xxx`. To make the liveness analysis work,
        # we have to register those variables as being assigned here
        bb.vars.assigned |= {return_var(i): node for i in range(self.num_returns)}
        bb.statements.append(node)
        return None

    def visit_Pass(self, node: ast.Pass, bb: BB, jumps: Jumps) -> Optional[BB]:
        return bb


class ExprBuilder(ast.NodeTransformer):
    """Builds an expression into a basic block."""

    branch_builder: "BranchBuilder"
    cfg: CFG
    bb: BB
    tmp_vars: Iterator[str]

    def __init__(self):
        self.branch_builder = BranchBuilder(self)
        self.tmp_vars = (f"%tmp{i}" for i in itertools.count())

    @classmethod
    def _make_var(cls, name: str, loc: Optional[ast.expr] = None) -> ast.Name:
        """Creates an `ast.Name` node."""
        node = ast.Name(id=name, ctx=ast.Load)
        if loc is not None:
            set_location(node, loc)
        return node

    @classmethod
    def _tmp_assign(cls, tmp_name: str, value: ast.expr, bb: BB) -> None:
        """Adds a temporary variable assignment to a basic block."""
        node = ast.Assign(targets=[cls._make_var(tmp_name, value)], value=value)
        set_location(node, value)
        bb.statements.append(node)
        # Mark variable as assigned for analysis later. Note that we point to the value
        # node instead of the assign node sine the temporary assign shouldn't be user
        # facing.
        bb.vars.update_used(value)
        bb.vars.assigned[tmp_name] = value

    def build(self, node: ast.expr, cfg: CFG, bb: BB) -> tuple[ast.expr, BB]:
        """Builds an expression into a CFG.

        The expression may be transformed and new basic blocks may be created (for
        example for `... if ... else ...` expressions). Returns the new expression and
        the final basic block in which the expression can be used."""
        self.cfg = cfg
        self.bb = bb
        return self.visit(node), self.bb

    def build_branch(self, node: ast.expr, cfg: CFG, bb: BB, true_bb: BB, false_bb: BB):
        return self.branch_builder.visit(node, cfg, bb, true_bb, false_bb)

    def visit_Name(self, node: ast.Name) -> ast.Name:
        self.bb.vars.update_used(node)
        return node

    def visit_NamedExpr(self, node: ast.NamedExpr) -> ast.Name:
        # This is an assignment expression, e.g. `x := 42`. We turn it into an
        # assignment statement and replace the expression with `x`.
        if not isinstance(node.target, ast.Name):
            raise InternalGuppyError(f"Unexpected assign target: {node.target}")
        assign = ast.Assign(targets=[node.target], value=self.visit(node.value))
        set_location(assign, node)
        self.bb.statements.append(assign)
        self.bb.vars.assigned[node.target.id] = node
        return node.target

    def visit_IfExp(self, node: ast.IfExp) -> ast.Name:
        if_bb, else_bb = self.cfg.new_bb(), self.cfg.new_bb()
        self.build_branch(node.test, self.cfg, self.bb, if_bb, else_bb)

        if_expr, if_bb = self.build(node.body, self.cfg, if_bb)
        else_expr, else_bb = self.build(node.orelse, self.cfg, else_bb)

        # Assign the result to a temporary variable
        tmp = next(self.tmp_vars)
        self._tmp_assign(tmp, if_expr, if_bb)
        self._tmp_assign(tmp, else_expr, else_bb)

        # Merge the temporary variables in a new BB
        merge_bb = self.cfg.new_bb(preds=[if_bb, else_bb])
        self.bb = merge_bb

        # The final value is stored in the temporary variable
        return self._make_var(tmp, node)

    def generic_visit(self, node: ast.AST) -> ast.AST:
        # Short-circuit expressions must be built using the `BranchBuilder`. However, we
        # can turn them into regular expressions by assigning True/False to a temporary
        # variable and merging the control-flow
        if BranchBuilder.is_short_circuit_expr(node):
            true_bb, false_bb = self.cfg.new_bb(), self.cfg.new_bb()
            self.build_branch(node, self.cfg, self.bb, true_bb, false_bb)
            true_const = set_location(ast.Constant(value=True), node)
            false_const = set_location(ast.Constant(value=False), node)
            tmp = next(self.tmp_vars)
            self._tmp_assign(tmp, true_const, true_bb)
            self._tmp_assign(tmp, false_const, false_bb)
            merge_bb = self.cfg.new_bb(preds=[true_bb, false_bb])
            self.bb = merge_bb
            return self._make_var(tmp, node)
        # For all other expressions, just recurse deeper with the node transformer
        return super().generic_visit(node)


class BranchBuilder(AstVisitor[None]):
    """Builds an expression and does branching based on the value.

    This builder should be used to handle all branching on boolean values since it
    handles short-circuit evaluation etc.
    """

    expr_builder: ExprBuilder

    def __init__(self, expr_builder: ExprBuilder) -> None:
        self.expr_builder = expr_builder

    @staticmethod
    def is_short_circuit_expr(node: ast.AST) -> bool:
        """Checks if an expression uses short-circuiting.

        Those expressions *must* be compiled using this builder.
        """
        return isinstance(node, ast.BoolOp) or (
            isinstance(node, ast.Compare) and len(node.comparators) > 1
        )

    def visit_BoolOp(
        self, node: ast.BoolOp, cfg: CFG, bb: BB, true_bb: BB, false_bb: BB
    ) -> None:
        # Add short-circuit evaluation of boolean expression. If there are more than 2
        # operators, we turn the flat operator list into a right-nested tree to allow
        # for recursive processing.
        assert len(node.values) > 1
        if len(node.values) > 2:
            r = ast.BoolOp(
                op=node.op,
                values=node.values[1:],
                lineno=node.values[0].lineno,
                col_offset=node.values[0].col_offset,
                end_lineno=node.values[-1].end_lineno,
                end_col_offset=node.values[-1].end_col_offset,
            )
            node.values = [node.values[0], r]
        [left, right] = node.values

        extra_bb = cfg.new_bb()
        if isinstance(node.op, ast.And):
            self.visit(left, cfg, bb, extra_bb, false_bb)
        elif isinstance(node.op, ast.Or):
            self.visit(left, cfg, bb, true_bb, extra_bb)
        else:
            raise InternalGuppyError(f"Unexpected BoolOp encountered: {node.op}")
        self.visit(right, cfg, extra_bb, true_bb, false_bb)

    def visit_UnaryOp(
        self, node: ast.UnaryOp, cfg: CFG, bb: BB, true_bb: BB, false_bb: BB
    ) -> None:
        # For `not` operator, we can just switch `true_bb` and `false_bb`
        if isinstance(node.op, ast.Not):
            self.visit(node.operand, cfg, bb, false_bb, true_bb)
        else:
            self.generic_visit(node, cfg, bb, true_bb, false_bb)

    def visit_Compare(
        self, node: ast.Compare, cfg: CFG, bb: BB, true_bb: BB, false_bb: BB
    ) -> None:
        # Support chained comparisons, e.g. `x <= 5 < y` by compiling to `x <= 5 and
        # 5 < y`. This way we get short-circuit evaluation for free.
        if len(node.comparators) > 1:
            comparators = [node.left] + node.comparators
            conj = ast.BoolOp(op=ast.And(), values=[])
            for left, op, right in zip(comparators[:-1], node.ops, comparators[1:]):
                comp = ast.Compare(
                    left=left,
                    ops=[op],
                    comparators=[right],
                    lineno=left.lineno,
                    col_offset=left.col_offset,
                    end_lineno=right.end_lineno,
                    end_col_offset=right.end_col_offset,
                )
                conj.values.append(comp)
            set_location(conj, node)
            self.visit_BoolOp(conj, cfg, bb, true_bb, false_bb)
        else:
            self.generic_visit(node, cfg, bb, true_bb, false_bb)

    def visit_IfExp(
        self, node: ast.IfExp, cfg: CFG, bb: BB, true_bb: BB, false_bb: BB
    ) -> None:
        if_bb, else_bb = cfg.new_bb(), cfg.new_bb()
        self.visit(node.test, cfg, bb, if_bb, else_bb)
        self.visit(node.body, cfg, if_bb, true_bb, false_bb)
        self.visit(node.orelse, cfg, else_bb, true_bb, false_bb)

    def generic_visit(
        self, node: ast.IfExp, cfg: CFG, bb: BB, true_bb: BB, false_bb: BB
    ) -> None:  # type: ignore
        # We can always fall back to building the node as a regular expression and using
        # the result as a branch predicate
        pred, bb = self.expr_builder.build(node, cfg, bb)
        bb.branch_pred = pred
        bb.vars.update_used(pred)
        cfg.link(bb, true_bb)
        cfg.link(bb, false_bb)


def is_functional_annotation(stmt: ast.stmt) -> bool:
    """Returns `True` iff the given statement is the functional pseudo-decorator.

    Pseudo-decorators are built using the matmul operator `@`, i.e. `_@functional`.
    """
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.BinOp):
        op = stmt.value
        if (
            isinstance(op.op, ast.MatMult)
            and isinstance(op.left, ast.Name)
            and isinstance(op.right, ast.Name)
        ):
            return op.left.id == "_" and op.right.id == "functional"
    return False
