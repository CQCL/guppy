"""Type checking code for control-flow graphs

Operates on CFGs produced by the `CFGBuilder`. Produces a `CheckedCFG` consisting of
`CheckedBB`s with inferred type signatures.
"""

import ast
import collections
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import ClassVar, Generic, TypeVar

from guppylang.ast_util import line_col
from guppylang.cfg.bb import BB
from guppylang.cfg.cfg import CFG, BaseCFG
from guppylang.checker.core import Context, Globals, Locals, Place, V, Variable
from guppylang.checker.expr_checker import ExprSynthesizer, to_bool
from guppylang.checker.stmt_checker import StmtChecker
from guppylang.diagnostic import Error, Note
from guppylang.error import GuppyError
from guppylang.tys.param import Parameter
from guppylang.tys.ty import InputFlags, Type

Row = Sequence[V]


@dataclass(frozen=True)
class Signature(Generic[V]):
    """The signature of a basic block.

    Stores the input/output variables with their types. Generic over the representation
    of program variables.
    """

    input_row: Row[V]
    output_rows: Sequence[Row[V]]  # One for each successor

    dummy_output_rows: Sequence[Row[V]] = field(default_factory=list)

    @staticmethod
    def empty() -> "Signature[V]":
        return Signature([], [], [])


@dataclass(eq=False)  # Disable equality to recover hash from `object`
class CheckedBB(BB, Generic[V]):
    """Basic block annotated with an input and output type signature.

    The signature is generic over the representation of program variables.
    """

    sig: Signature[V] = field(default_factory=Signature.empty)


class CheckedCFG(BaseCFG[CheckedBB[V]], Generic[V]):
    input_tys: list[Type]
    output_ty: Type

    def __init__(self, input_tys: list[Type], output_ty: Type) -> None:
        super().__init__([])
        self.input_tys = input_tys
        self.output_ty = output_ty


def check_cfg(
    cfg: CFG,
    inputs: Row[Variable],
    return_ty: Type,
    generic_params: dict[str, Parameter],
    func_name: str,
    globals: Globals,
) -> CheckedCFG[Place]:
    """Type checks a control-flow graph.

    Annotates the basic blocks with input and output type signatures and removes
    unreachable blocks. Note that the inputs/outputs are annotated in the form of
    *places* rather than just variables.
    """
    # First, we need to run program analysis
    ass_before = {v.name for v in inputs}
    inout_vars = [v for v in inputs if InputFlags.Inout in v.flags]
    cfg.analyze(ass_before, ass_before, [v.name for v in inout_vars])

    # We start by compiling the entry BB
    checked_cfg: CheckedCFG[Variable] = CheckedCFG([v.ty for v in inputs], return_ty)
    checked_cfg.entry_bb = check_bb(
        cfg.entry_bb, checked_cfg, inputs, return_ty, generic_params, globals
    )
    compiled = {cfg.entry_bb: checked_cfg.entry_bb}

    # Visit all control-flow edges in BFS order. We can't just do a normal loop over
    # all BBs since the input types for a BB are computed by checking a predecessor.
    # We do BFS instead of DFS to get a better error ordering.
    queue = collections.deque(
        (checked_cfg.entry_bb, i, succ)
        # We enumerate the successor starting from the back, so we start with the `True`
        # branch. This way, we find errors in a more natural order
        for i, succ in reverse_enumerate(
            cfg.entry_bb.successors + cfg.entry_bb.dummy_successors
        )
    )
    while len(queue) > 0:
        pred, num_output, bb = queue.popleft()
        pred_outputs = [*pred.sig.output_rows, *pred.sig.dummy_output_rows]
        input_row = [
            Variable(v.name, v.ty, v.defined_at, v.flags)
            for v in pred_outputs[num_output]
        ]

        if bb in compiled:
            # If the BB was already compiled, we just have to check that the signatures
            # match.
            check_rows_match(input_row, compiled[bb].sig.input_row, bb)
        else:
            # Otherwise, check the BB and enqueue its successors
            checked_bb = check_bb(
                bb, checked_cfg, input_row, return_ty, generic_params, globals
            )
            queue += [
                # We enumerate the successor starting from the back, so we start with
                # the `True` branch. This way, we find errors in a more natural order
                (checked_bb, i, succ)
                for i, succ in reverse_enumerate(bb.successors)
            ]
            compiled[bb] = checked_bb

        # Link up BBs in the checked CFG, excluding the unreachable ones
        if bb.reachable:
            compiled[bb].predecessors.append(pred)
            pred.successors[num_output] = compiled[bb]

    # The exit BB might be unreachable. In that case it won't be visited above and we
    # have to handle it here
    if cfg.exit_bb not in compiled:
        assert not cfg.exit_bb.reachable
        compiled[cfg.exit_bb] = CheckedBB(
            cfg.exit_bb.idx, checked_cfg, reachable=False, sig=Signature(inout_vars, [])
        )

    required_bbs = [bb for bb in cfg.bbs if bb.reachable or bb.is_exit]
    checked_cfg.bbs = [compiled[bb] for bb in required_bbs]
    checked_cfg.exit_bb = compiled[cfg.exit_bb]
    checked_cfg.live_before = {compiled[bb]: cfg.live_before[bb] for bb in required_bbs}
    checked_cfg.ass_before = {compiled[bb]: cfg.ass_before[bb] for bb in required_bbs}
    checked_cfg.maybe_ass_before = {
        compiled[bb]: cfg.maybe_ass_before[bb] for bb in required_bbs
    }

    # Finally, run the linearity check
    from guppylang.checker.linearity_checker import check_cfg_linearity

    linearity_checked_cfg = check_cfg_linearity(checked_cfg, func_name, globals)

    return linearity_checked_cfg


@dataclass(frozen=True)
class VarNotDefinedError(Error):
    title: ClassVar[str] = "Variable not defined"
    span_label: ClassVar[str] = "`{var}` is not defined"
    var: str


@dataclass(frozen=True)
class VarMaybeNotDefinedError(Error):
    title: ClassVar[str] = "Variable not defined"
    var: str

    @dataclass(frozen=True)
    class BadBranch(Note):
        span_label: ClassVar[str] = "... if this expression is `{truth_value}`"
        var: str
        truth_value: bool

    @property
    def rendered_span_label(self) -> str:
        s = f"`{self.var}` might be undefined"
        if self.children:
            s += " ..."
        return s


@dataclass(frozen=True)
class BranchTypeError(Error):
    title: ClassVar[str] = "Different types"
    span_label: ClassVar[str] = "{ident} may refer to different types"
    ident: str

    @dataclass(frozen=True)
    class TypeHint(Note):
        span_label: ClassVar[str] = "This is of type `{ty}`"
        ty: Type


def check_bb(
    bb: BB,
    checked_cfg: CheckedCFG[Variable],
    inputs: Row[Variable],
    return_ty: Type,
    generic_params: dict[str, Parameter],
    globals: Globals,
) -> CheckedBB[Variable]:
    cfg = bb.containing_cfg

    # For the entry BB we have to separately check that all used variables are
    # defined. For all other BBs, this will be checked when compiling a predecessor.
    if bb == cfg.entry_bb:
        assert len(bb.predecessors) == 0
        for x, use in bb.vars.used.items():
            if x not in cfg.ass_before[bb] and x not in globals:
                raise GuppyError(VarNotDefinedError(use, x))

    # Check the basic block
    ctx = Context(globals, Locals({v.name: v for v in inputs}), generic_params)
    checked_stmts = StmtChecker(ctx, bb, return_ty).check_stmts(bb.statements)

    # If we branch, we also have to check the branch predicate
    if len(bb.successors) > 1:
        assert bb.branch_pred is not None
        bb.branch_pred, ty = ExprSynthesizer(ctx).synthesize(bb.branch_pred)
        bb.branch_pred, _ = to_bool(bb.branch_pred, ty, ctx)

    for succ in bb.successors + bb.dummy_successors:
        for x, use_bb in cfg.live_before[succ].items():
            # Check that the variables requested by the successor are defined
            if x not in ctx.locals and x not in ctx.globals:
                # If the variable is defined on *some* paths, we can give a more
                # informative error message
                if x in cfg.maybe_ass_before[use_bb]:
                    err = VarMaybeNotDefinedError(use_bb.vars.used[x], x)
                    if bad_branch := diagnose_maybe_undefined(use_bb, x, cfg):
                        branch_expr, truth_value = bad_branch
                        note = VarMaybeNotDefinedError.BadBranch(
                            branch_expr, x, truth_value
                        )
                        err.add_sub_diagnostic(note)
                    raise GuppyError(err)
                raise GuppyError(VarNotDefinedError(use_bb.vars.used[x], x))

    # Finally, we need to compute the signature of the basic block
    outputs = [
        [ctx.locals[x] for x in cfg.live_before[succ] if x in ctx.locals]
        for succ in bb.successors
    ]
    dummy_outputs = [
        [ctx.locals[x] for x in cfg.live_before[succ] if x in ctx.locals]
        for succ in bb.dummy_successors
    ]

    # Also prepare the successor list so we can fill it in later
    checked_bb = CheckedBB(
        bb.idx,
        checked_cfg,
        checked_stmts,
        reachable=bb.reachable,
        sig=Signature(inputs, outputs, dummy_outputs),
    )
    checked_bb.successors = [None] * len(bb.successors)  # type: ignore[list-item]
    checked_bb.branch_pred = bb.branch_pred
    return checked_bb


def check_rows_match(row1: Row[Variable], row2: Row[Variable], bb: BB) -> None:
    """Checks that the types of two rows match up.

    Otherwise, an error is thrown, alerting the user that a variable has different
    types on different control-flow paths.
    """
    map1, map2 = {v.name: v for v in row1}, {v.name: v for v in row2}
    assert map1.keys() == map2.keys()
    for x in map1:
        v1, v2 = map1[x], map2[x]
        if v1.ty != v2.ty:
            # In the error message, we want to mention the variable that was first
            # defined at the start.
            if (
                v1.defined_at
                and v2.defined_at
                and line_col(v2.defined_at) < line_col(v1.defined_at)
            ):
                v1, v2 = v2, v1
            # We shouldn't mention temporary variables (starting with `%`)
            # in error messages:
            ident = "Expression" if v1.name.startswith("%") else f"Variable `{v1.name}`"
            use = bb.containing_cfg.live_before[bb][v1.name].vars.used[v1.name]
            err = BranchTypeError(use, ident)
            err.add_sub_diagnostic(BranchTypeError.TypeHint(v1.defined_at, v1.ty))
            err.add_sub_diagnostic(BranchTypeError.TypeHint(v2.defined_at, v2.ty))
            raise GuppyError(err)


def diagnose_maybe_undefined(
    bb: BB, x: str, cfg: BaseCFG[BB]
) -> tuple[ast.expr, bool] | None:
    """Given a BB and a variable `x`, tries to find a branch where one of the successors
    leads to an assignment of `x` while the other one does not.

    Returns the branch condition and a flag whether the value being `True` leads to the
    undefined path. Returns `None` if no such branch can be found.
    """
    assert x in cfg.maybe_ass_before[bb]
    # Find all BBs that can reach this BB and which ones of those assign `x`
    ancestors = list(cfg.ancestors(bb))
    assigns = [anc for anc in ancestors if x in anc.vars.assigned]
    # Compute which ancestors can possibly reach an assignment
    reaches_assignment = set(cfg.ancestors(*assigns))
    # Try to find a branching BB where one of paths can reach an assignment, while the
    # other one cannot
    for anc in ancestors:
        match anc.successors:
            case [true_succ, false_succ]:
                assert anc.branch_pred is not None
                true_reaches_assignment = true_succ in reaches_assignment
                false_reaches_assignment = false_succ in reaches_assignment
                if true_reaches_assignment != false_reaches_assignment:
                    return anc.branch_pred, true_reaches_assignment
    return None


T = TypeVar("T")


def reverse_enumerate(xs: list[T]) -> Iterator[tuple[int, T]]:
    """Enumerates a list in reverse order.

    Equivalent to `reversed(list(enumerate(data)))` without creating an intermediate
    list.
    """
    for i in range(len(xs) - 1, -1, -1):
        yield i, xs[i]
