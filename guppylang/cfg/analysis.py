from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Generic, TypeVar

from guppylang.cfg.bb import BB, VariableStats, VId

# Type variable for the lattice domain
T = TypeVar("T")

# Analysis result is a mapping from basic blocks to lattice values
Result = dict[BB, T]


class Analysis(Generic[T], ABC):
    """Abstract base class for a program analysis pass over the lattice `T`"""

    def eq(self, t1: T, t2: T, /) -> bool:
        """Equality on lattice values"""
        return t1 == t2

    @abstractmethod
    def include_unreachable(self) -> bool:
        """Whether unreachable BBs and jumps should be taken into account for the
        analysis."""

    @abstractmethod
    def initial(self) -> T:
        """Initial lattice value"""

    @abstractmethod
    def join(self, *ts: T) -> T:
        """Lattice join operation"""

    @abstractmethod
    def run(self, bbs: Iterable[BB]) -> Result[T]:
        """Runs the analysis pass.

        Returns a mapping from basic blocks to lattice values at the start of each BB.
        """


class ForwardAnalysis(Generic[T], Analysis[T], ABC):
    """Abstract base class for a program analysis pass running in forward direction."""

    @abstractmethod
    def apply_bb(self, val_before: T, bb: BB, /) -> T:
        """Transformation a basic block applies to a lattice value"""

    def run(self, bbs: Iterable[BB]) -> Result[T]:
        """Runs the analysis pass.

        Returns a mapping from basic blocks to lattice values at the start of each BB.
        """
        if not self.include_unreachable():
            bbs = [bb for bb in bbs if bb.reachable]
        vals_before = {bb: self.initial() for bb in bbs}  # return value
        vals_after = {bb: self.apply_bb(vals_before[bb], bb) for bb in bbs}  # cache
        queue = set(bbs)
        while len(queue) > 0:
            bb = queue.pop()
            preds = (
                bb.predecessors + bb.dummy_predecessors
                if self.include_unreachable()
                else bb.predecessors
            )
            vals_before[bb] = self.join(*(vals_after[pred] for pred in preds))
            val_after = self.apply_bb(vals_before[bb], bb)
            if not self.eq(val_after, vals_after[bb]):
                vals_after[bb] = val_after
                queue.update(bb.successors)
        return vals_before


class BackwardAnalysis(Generic[T], Analysis[T], ABC):
    """Abstract base class for a program analysis pass running in backward direction."""

    @abstractmethod
    def apply_bb(self, val_after: T, bb: BB, /) -> T:
        """Transformation a basic block applies to a lattice value"""

    def run(self, bbs: Iterable[BB]) -> Result[T]:
        """Runs the analysis pass.

        Returns a mapping from basic blocks to lattice values at the start of each BB.
        """
        vals_before = {bb: self.initial() for bb in bbs}
        queue = set(bbs)
        while len(queue) > 0:
            bb = queue.pop()
            succs = (
                bb.successors + bb.dummy_successors
                if self.include_unreachable()
                else bb.successors
            )
            val_after = self.join(*(vals_before[succ] for succ in succs))
            val_before = self.apply_bb(val_after, bb)
            if not self.eq(vals_before[bb], val_before):
                vals_before[bb] = val_before
                queue.update(bb.predecessors)
        return vals_before


# For live variable analysis, we also store a BB in which a use occurs as evidence of
# liveness.
LivenessDomain = dict[VId, BB]


class LivenessAnalysis(Generic[VId], BackwardAnalysis[LivenessDomain[VId]]):
    """Live variable analysis pass.

    Computes the variables that are live before the execution of each BB. The analysis
    runs over the lattice of mappings from variable names to BBs containing a use.
    """

    stats: dict[BB, VariableStats[VId]]

    def __init__(
        self,
        stats: dict[BB, VariableStats[VId]],
        initial: LivenessDomain[VId] | None = None,
        include_unreachable: bool = False,
    ) -> None:
        self.stats = stats
        self._initial = initial or {}
        self._include_unreachable = include_unreachable

    def eq(self, live1: LivenessDomain[VId], live2: LivenessDomain[VId]) -> bool:
        # Only check that both contain the same variables. We don't care about the BB
        # in which the use occurs, we just need any one, to report to the user.
        return live1.keys() == live2.keys()

    def initial(self) -> LivenessDomain[VId]:
        return self._initial

    def include_unreachable(self) -> bool:
        return self._include_unreachable

    def join(self, *ts: LivenessDomain[VId]) -> LivenessDomain[VId]:
        res: LivenessDomain[VId] = {}
        for t in ts:
            res |= t
        return res

    def apply_bb(self, live_after: LivenessDomain[VId], bb: BB) -> LivenessDomain[VId]:
        stats = self.stats[bb]
        return {x: bb for x in stats.used} | {
            x: b for x, b in live_after.items() if x not in stats.assigned
        }


# Set of variables that are definitely assigned at the start of a BB
DefAssignmentDomain = set[VId]

# Set of variables that are assigned on (at least) some paths to a BB. Definitely
# assigned variables are a subset of this
MaybeAssignmentDomain = set[VId]

# For assignment analysis, we do definite- and maybe-assignment in one pass
AssignmentDomain = tuple[DefAssignmentDomain[VId], MaybeAssignmentDomain[VId]]


class AssignmentAnalysis(Generic[VId], ForwardAnalysis[AssignmentDomain[VId]]):
    """Assigned variable analysis pass.

    Computes the set of variables (i.e. `V`s) that are definitely assigned at the start
    of a BB. Additionally, we compute the set of variables that are assigned on (at
    least) some paths to a BB (the definitely assigned variables are a subset of this).
    """

    stats: dict[BB, VariableStats[VId]]
    all_vars: set[VId]
    ass_before_entry: set[VId]
    maybe_ass_before_entry: set[VId]

    def __init__(
        self,
        stats: dict[BB, VariableStats[VId]],
        ass_before_entry: set[VId],
        maybe_ass_before_entry: set[VId],
        include_unreachable: bool = False,
    ) -> None:
        """Constructs an `AssignmentAnalysis` pass for a CFG.

        Also takes a set variables that are definitely assigned before the entry of the
        CFG (for example function arguments).
        """
        assert ass_before_entry.issubset(maybe_ass_before_entry)
        self.stats = stats
        self.ass_before_entry = ass_before_entry
        self.maybe_ass_before_entry = maybe_ass_before_entry
        self.all_vars = (
            set.union(*(set(stat.assigned.keys()) for stat in stats.values()))
            | ass_before_entry
        )
        self._include_unreachable = include_unreachable

    def initial(self) -> AssignmentDomain[VId]:
        # Note that definite assignment must start with `all_vars` instead of only
        # `ass_before_entry` since we want to compute the *greatest* fixpoint.
        return self.all_vars, self.maybe_ass_before_entry

    def include_unreachable(self) -> bool:
        return self._include_unreachable

    def join(self, *ts: AssignmentDomain[VId]) -> AssignmentDomain[VId]:
        # We always include the variables that are definitely assigned before the entry,
        # even if the join is empty
        if len(ts) == 0:
            return self.ass_before_entry, self.ass_before_entry

        def_ass = set.intersection(*(def_ass for def_ass, _ in ts))
        maybe_ass = set.union(*(maybe_ass for _, maybe_ass in ts))
        return def_ass, maybe_ass

    def apply_bb(
        self, val_before: AssignmentDomain[VId], bb: BB
    ) -> AssignmentDomain[VId]:
        stats = self.stats[bb]
        def_ass_before, maybe_ass_before = val_before
        return (
            def_ass_before | stats.assigned.keys(),
            maybe_ass_before | stats.assigned.keys(),
        )

    def run_unpacked(
        self, bbs: Iterable[BB]
    ) -> tuple[Result[DefAssignmentDomain[VId]], Result[MaybeAssignmentDomain[VId]]]:
        """Runs the analysis and unpacks the definite- and maybe-assignment results."""
        res = self.run(bbs)
        return {bb: res[bb][0] for bb in res}, {bb: res[bb][1] for bb in res}
