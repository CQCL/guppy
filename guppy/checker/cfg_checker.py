"""Type checking code for control-flow graphs

Operates on CFGs produced by the `CFGBuilder`. Produces a `CheckedCFG` consisting of
`CheckedBB`s with inferred type signatures.
"""

import collections
from dataclasses import dataclass
from typing import Sequence

from guppy.ast_util import line_col
from guppy.cfg.bb import BB
from guppy.cfg.cfg import CFG, BaseCFG
from guppy.checker.core import Globals, Context

from guppy.checker.core import Variable
from guppy.checker.expr_checker import ExprSynthesizer, to_bool
from guppy.checker.stmt_checker import StmtChecker
from guppy.error import GuppyError
from guppy.gtypes import GuppyType


VarRow = Sequence[Variable]


@dataclass(frozen=True)
class Signature:
    """The signature of a basic block.

    Stores the input/output variables with their types.
    """

    input_row: VarRow
    output_rows: Sequence[VarRow]  # One for each successor

    @staticmethod
    def empty() -> "Signature":
        return Signature([], [])


@dataclass(eq=False)  # Disable equality to recover hash from `object`
class CheckedBB(BB):
    """Basic block annotated with an input and output type signature."""

    sig: Signature = Signature.empty()


class CheckedCFG(BaseCFG[CheckedBB]):
    input_tys: list[GuppyType]
    output_ty: GuppyType

    def __init__(self, input_tys: list[GuppyType], output_ty: GuppyType) -> None:
        super().__init__([])
        self.input_tys = input_tys
        self.output_ty = output_ty


def check_cfg(
    cfg: CFG, inputs: VarRow, return_ty: GuppyType, globals: Globals
) -> CheckedCFG:
    """Type checks a control-flow graph.

    Annotates the basic blocks with input and output type signatures and removes
    unreachable blocks.
    """
    # First, we need to run program analysis
    ass_before = set(v.name for v in inputs)
    cfg.analyze(ass_before, ass_before)

    # We start by compiling the entry BB
    checked_cfg = CheckedCFG([v.ty for v in inputs], return_ty)
    checked_cfg.entry_bb = check_bb(
        cfg.entry_bb, checked_cfg, inputs, return_ty, globals
    )
    compiled = {cfg.entry_bb: checked_cfg.entry_bb}

    # Visit all control-flow edges in BFS order. We can't just do a normal loop over
    # all BBs since the input types for a BB are computed by checking a predecessor.
    # We do BFS instead of DFS to get a better error ordering.
    queue = collections.deque(
        (checked_cfg.entry_bb, i, succ)
        for i, succ in enumerate(cfg.entry_bb.successors)
    )
    while len(queue) > 0:
        pred, num_output, bb = queue.popleft()
        input_row = [
            Variable(v.name, v.ty, v.defined_at, None)
            for v in pred.sig.output_rows[num_output]
        ]

        if bb in compiled:
            # If the BB was already compiled, we just have to check that the signatures
            # match.
            check_rows_match(input_row, compiled[bb].sig.input_row, bb)
        else:
            # Otherwise, check the BB and enqueue its successors
            checked_bb = check_bb(bb, checked_cfg, input_row, return_ty, globals)
            queue += [(checked_bb, i, succ) for i, succ in enumerate(bb.successors)]
            compiled[bb] = checked_bb

        # Link up BBs in the checked CFG
        compiled[bb].predecessors.append(pred)
        pred.successors[num_output] = compiled[bb]

    checked_cfg.bbs = list(compiled.values())
    checked_cfg.exit_bb = compiled[cfg.exit_bb]  # TODO: Fails if exit is unreachable
    checked_cfg.live_before = {compiled[bb]: cfg.live_before[bb] for bb in cfg.bbs}
    checked_cfg.ass_before = {compiled[bb]: cfg.ass_before[bb] for bb in cfg.bbs}
    checked_cfg.maybe_ass_before = {
        compiled[bb]: cfg.maybe_ass_before[bb] for bb in cfg.bbs
    }
    return checked_cfg


def check_bb(
    bb: BB,
    checked_cfg: CheckedCFG,
    inputs: VarRow,
    return_ty: GuppyType,
    globals: Globals,
) -> CheckedBB:
    cfg = bb.containing_cfg

    # For the entry BB we have to separately check that all used variables are
    # defined. For all other BBs, this will be checked when compiling a predecessor.
    if bb == cfg.entry_bb:
        assert len(bb.predecessors) == 0
        for x, use in bb.vars.used.items():
            if x not in cfg.ass_before[bb] and x not in globals.values:
                raise GuppyError(f"Variable `{x}` is not defined", use)

    # Check the basic block
    ctx = Context(globals, {v.name: v for v in inputs})
    checked_stmts = StmtChecker(ctx, bb, return_ty).check_stmts(bb.statements)

    # If we branch, we also have to check the branch predicate
    if len(bb.successors) > 1:
        assert bb.branch_pred is not None
        bb.branch_pred, ty = ExprSynthesizer(ctx).synthesize(bb.branch_pred)
        bb.branch_pred, _ = to_bool(bb.branch_pred, ty, ctx)

    for succ in bb.successors:
        for x, use_bb in cfg.live_before[succ].items():
            # Check that the variables requested by the successor are defined
            if x not in ctx.locals and x not in ctx.globals.values:
                # If the variable is defined on *some* paths, we can give a more
                # informative error message
                if x in cfg.maybe_ass_before[use_bb]:
                    # TODO: This should be "Variable x is not defined when coming
                    #  from {bb}". But for this we need a way to associate BBs with
                    #  source locations.
                    raise GuppyError(
                        f"Variable `{x}` is not defined on all control-flow paths.",
                        use_bb.vars.used[x],
                    )
                raise GuppyError(f"Variable `{x}` is not defined", use_bb.vars.used[x])

            # We have to check that used linear variables are not being outputted
            if x in ctx.locals:
                var = ctx.locals[x]
                if var.ty.linear and var.used:
                    raise GuppyError(
                        f"Variable `{x}` with linear type `{var.ty}` was "
                        "already used (at {0})",
                        cfg.live_before[succ][x].vars.used[x],
                        [var.used],
                    )

        # On the other hand, unused linear variables *must* be outputted
        for x, var in ctx.locals.items():
            if var.ty.linear and not var.used and x not in cfg.live_before[succ]:
                # TODO: This should be "Variable x with linear type ty is not
                #  used in {bb}". But for this we need a way to associate BBs with
                #  source locations.
                raise GuppyError(
                    f"Variable `{x}` with linear type `{var.ty}` is "
                    "not used on all control-flow paths",
                    var.defined_at,
                )

    # Finally, we need to compute the signature of the basic block
    outputs = [
        [ctx.locals[x] for x in cfg.live_before[succ] if x in ctx.locals]
        for succ in bb.successors
    ]

    # Also prepare the successor list so we can fill it in later
    checked_bb = CheckedBB(
        bb.idx, checked_cfg, checked_stmts, sig=Signature(inputs, outputs)
    )
    checked_bb.successors = [None] * len(bb.successors)  # type: ignore
    checked_bb.branch_pred = bb.branch_pred
    return checked_bb


def check_rows_match(row1: VarRow, row2: VarRow, bb: BB) -> None:
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
            raise GuppyError(
                f"{ident} can refer to different types: "
                f"`{v1.ty}` (at {{}}) vs `{v2.ty}` (at {{}})",
                bb.containing_cfg.live_before[bb][v1.name].vars.used[v1.name],
                [v1.defined_at, v2.defined_at],
            )
