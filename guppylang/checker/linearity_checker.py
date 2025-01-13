"""Linearity checking

Linearity checking across control-flow is done by the `CFGChecker`.
"""

import ast
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from enum import Enum, auto
from typing import TYPE_CHECKING, NamedTuple, TypeGuard

from guppylang.ast_util import AstNode, find_nodes, get_type
from guppylang.cfg.analysis import LivenessAnalysis, LivenessDomain
from guppylang.cfg.bb import BB, VariableStats
from guppylang.checker.cfg_checker import CheckedBB, CheckedCFG, Row, Signature
from guppylang.checker.core import (
    FieldAccess,
    Globals,
    Locals,
    Place,
    PlaceId,
    SubscriptAccess,
    Variable,
)
from guppylang.checker.errors.linearity import (
    AlreadyUsedError,
    BorrowShadowedError,
    BorrowSubPlaceUsedError,
    ComprAlreadyUsedError,
    DropAfterCallError,
    LinearCaptureError,
    LinearPartialApplyError,
    MoveOutOfSubscriptError,
    NotOwnedError,
    PlaceNotUsedError,
    UnnamedExprNotUsedError,
    UnnamedFieldNotUsedError,
    UnnamedSubscriptNotUsedError,
)
from guppylang.definition.custom import CustomFunctionDef
from guppylang.definition.value import CallableDef
from guppylang.error import GuppyError, GuppyTypeError
from guppylang.nodes import (
    AnyCall,
    CheckedNestedFunctionDef,
    DesugaredArrayComp,
    DesugaredGenerator,
    DesugaredListComp,
    FieldAccessAndDrop,
    GlobalCall,
    InoutReturnSentinel,
    LocalCall,
    PartialApply,
    PlaceNode,
    SubscriptAccessAndDrop,
    TensorCall,
)
from guppylang.tys.ty import (
    FuncInput,
    FunctionType,
    InputFlags,
    StructType,
)

if TYPE_CHECKING:
    from guppylang.diagnostic import Error


class UseKind(Enum):
    """The different ways places can be used."""

    #: A classical value is copied
    COPY = auto()

    #: A value is borrowed when passing it to a function
    BORROW = auto()

    #: Ownership of an owned value is transferred by passing it to a function
    CONSUME = auto()

    #: Ownership of an owned value is transferred by returning it
    RETURN = auto()

    #: An owned value is renamed or stored in a tuple/list
    MOVE = auto()

    @property
    def indicative(self) -> str:
        """Describes a use in an indicative mood.

        For example: "You cannot *consume* this qubit."
        """
        return self.name.lower()

    @property
    def subjunctive(self) -> str:
        """Describes a use in a subjunctive mood.

        For example: "This qubit cannot be *consumed*"
        """
        match self:
            case UseKind.COPY:
                return "copied"
            case UseKind.BORROW:
                return "borrowed"
            case UseKind.CONSUME:
                return "consumed"
            case UseKind.RETURN:
                return "returned"
            case UseKind.MOVE:
                return "moved"


class Use(NamedTuple):
    """Records data associated with a use of a place."""

    #: The AST node corresponding to the use
    node: AstNode

    #: The kind of use, i.e. is the value consumed, borrowed, returned, ...?
    kind: UseKind


class Scope(Locals[PlaceId, Place]):
    """Scoped collection of assigned places indexed by their id.

    Keeps track of which places have already been used.
    """

    parent_scope: "Scope | None"
    used_local: dict[PlaceId, Use]
    used_parent: dict[PlaceId, Use]

    def __init__(self, parent: "Scope | None" = None):
        self.used_local = {}
        self.used_parent = {}
        super().__init__({}, parent)

    def used(self, x: PlaceId) -> Use | None:
        """Checks whether a place has already been used."""
        if x in self.vars:
            return self.used_local.get(x, None)
        assert self.parent_scope is not None
        return self.parent_scope.used(x)

    def use(self, x: PlaceId, node: AstNode, kind: UseKind) -> None:
        """Records a use of a place.

        Works for places in the current scope as well as places in any parent scope.
        """
        if x in self.vars:
            self.used_local[x] = Use(node, kind)
        else:
            assert self.parent_scope is not None
            assert x in self.parent_scope
            self.used_parent[x] = Use(node, kind)
            self.parent_scope.use(x, node, kind)

    def assign(self, place: Place) -> None:
        """Records an assignment of a place."""
        assert place.defined_at is not None
        x = place.id
        self.vars[x] = place
        if x in self.used_local:
            self.used_local.pop(x)

    def stats(self) -> VariableStats[PlaceId]:
        assigned = {}
        for x, place in self.vars.items():
            assert place.defined_at is not None
            assigned[x] = place.defined_at
        used = {x: use.node for x, use in self.used_parent.items()}
        return VariableStats(assigned, used)


class BBLinearityChecker(ast.NodeVisitor):
    """AST visitor that checks linearity for a single basic block."""

    scope: Scope
    stats: VariableStats[PlaceId]
    func_name: str
    func_inputs: dict[PlaceId, Variable]
    globals: Globals

    def check(
        self,
        bb: "CheckedBB[Variable]",
        is_entry: bool,
        func_name: str,
        func_inputs: dict[PlaceId, Variable],
        globals: Globals,
    ) -> Scope:
        # Manufacture a scope that holds all places that are live at the start
        # of this BB
        input_scope = Scope()
        for var in bb.sig.input_row:
            for place in leaf_places(var):
                input_scope.assign(place)
        self.func_name = func_name
        self.func_inputs = func_inputs
        self.globals = globals

        # Open up a new nested scope to check the BB contents. This way we can track
        # when we use variables from the outside vs ones assigned in this BB. The only
        # exception is the entry BB since function arguments should be treated as part
        # of the entry BB
        self.scope = input_scope if is_entry else Scope(input_scope)

        for stmt in bb.statements:
            self.visit(stmt)
        if bb.branch_pred:
            self.visit(bb.branch_pred)
        return self.scope

    @contextmanager
    def new_scope(self) -> Generator[Scope, None, None]:
        scope, new_scope = self.scope, Scope(self.scope)
        self.scope = new_scope
        yield new_scope
        self.scope = scope

    def visit_PlaceNode(
        self,
        node: PlaceNode,
        /,
        use_kind: UseKind = UseKind.MOVE,
        is_call_arg: AnyCall | None = None,
    ) -> None:
        # Usage of borrowed variables is generally forbidden. The only exception is
        # letting them be reborrowed by another function call. In that case, our
        # `_visit_call_args` helper will set `use_kind=UseKind.BORROW`.
        is_inout_arg = use_kind == UseKind.BORROW
        if is_inout_var(node.place) and not is_inout_arg:
            err: Error = NotOwnedError(
                node,
                node.place,
                use_kind,
                is_call_arg is not None,
                self._call_name(is_call_arg),
                self.func_name,
            )
            arg_span = self.func_inputs[node.place.root.id].defined_at
            err.add_sub_diagnostic(NotOwnedError.MakeOwned(arg_span))
            raise GuppyError(err)
        # Places involving subscripts are handled differently since we ignore everything
        # after the subscript for the purposes of linearity checking
        if subscript := contains_subscript(node.place):
            if not is_inout_arg and subscript.parent.ty.linear:
                err = MoveOutOfSubscriptError(node, use_kind, subscript.parent)
                err.add_sub_diagnostic(MoveOutOfSubscriptError.Explanation(None))
                raise GuppyError(err)
            self.visit(subscript.item_expr)
            self.scope.assign(subscript.item)
            # Visiting the `__getitem__(place.parent, place.item)` call ensures that we
            # linearity-check the parent and element.
            self.visit(subscript.getitem_call)
        # For all other places, we record uses of all leaves
        else:
            for place in leaf_places(node.place):
                x = place.id
                if (prev_use := self.scope.used(x)) and place.ty.linear:
                    err = AlreadyUsedError(node, place, use_kind)
                    err.add_sub_diagnostic(
                        AlreadyUsedError.PrevUse(prev_use.node, prev_use.kind)
                    )
                    raise GuppyError(err)
                self.scope.use(x, node, use_kind)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        self._check_assign_targets(node.targets)

        # Check that borrowed vars are not being shadowed. This would also be caught by
        # the dataflow analysis later, however we can give nicer error messages here.
        [target] = node.targets
        for tgt in find_nodes(lambda n: isinstance(n, PlaceNode), target):
            assert isinstance(tgt, PlaceNode)
            if tgt.place.id in self.func_inputs:
                entry_place = self.func_inputs[tgt.place.id]
                if is_inout_var(entry_place):
                    err = BorrowShadowedError(tgt.place.defined_at, entry_place)
                    err.add_sub_diagnostic(BorrowShadowedError.Rename(None))
                    raise GuppyError(err)

    def visit_Return(self, node: ast.Return) -> None:
        # Intercept returns of places, so we can set the appropriate `use_kind` to get
        # nicer error messages
        if isinstance(node.value, PlaceNode):
            self.visit_PlaceNode(node.value, use_kind=UseKind.RETURN)
        elif isinstance(node.value, ast.Tuple):
            for elt in node.value.elts:
                if isinstance(elt, PlaceNode):
                    self.visit_PlaceNode(elt, use_kind=UseKind.RETURN)
                else:
                    self.visit(elt)
        elif node.value:
            self.visit(node.value)

    def _visit_call_args(self, func_ty: FunctionType, call: AnyCall) -> None:
        """Helper function to check the arguments of a function call.

        Populates the `use_kind` kwarg of `visit_PlaceNode` in case some of the
        arguments are places.
        """
        for inp, arg in zip(func_ty.inputs, call.args, strict=True):
            if isinstance(arg, PlaceNode):
                use_kind = (
                    UseKind.BORROW if InputFlags.Inout in inp.flags else UseKind.CONSUME
                )
                self.visit_PlaceNode(arg, use_kind=use_kind, is_call_arg=call)
            else:
                self.visit(arg)

    def _reassign_inout_args(self, func_ty: FunctionType, call: AnyCall) -> None:
        """Helper function to reassign the borrowed arguments after a function call."""
        for inp, arg in zip(func_ty.inputs, call.args, strict=True):
            if InputFlags.Inout in inp.flags:
                match arg:
                    case PlaceNode(place=place):
                        self._reassign_single_inout_arg(place, place.defined_at or arg)
                    case arg if inp.ty.linear:
                        err = DropAfterCallError(arg, inp.ty, self._call_name(call))
                        err.add_sub_diagnostic(DropAfterCallError.Assign(None))
                        raise GuppyError(err)

    def _reassign_single_inout_arg(self, place: Place, node: AstNode) -> None:
        """Helper function to reassign a single borrowed argument after a function
        call."""
        # Places involving subscripts are given back by visiting the `__setitem__` call
        if subscript := contains_subscript(place):
            assert subscript.setitem_call is not None
            self.visit(subscript.setitem_call)
            self._reassign_single_inout_arg(subscript.parent, node)
        else:
            for leaf in leaf_places(place):
                assert not isinstance(leaf, SubscriptAccess)
                leaf = leaf.replace_defined_at(node)
                self.scope.assign(leaf)

    def _call_name(self, node: AnyCall | None) -> str | None:
        """Tries to extract the name of a called function from a call AST node."""
        if isinstance(node, LocalCall):
            return node.func.id if isinstance(node.func, ast.Name) else None
        elif isinstance(node, GlobalCall):
            return self.globals[node.def_id].name
        return None

    def visit_GlobalCall(self, node: GlobalCall) -> None:
        func = self.globals[node.def_id]
        assert isinstance(func, CallableDef)
        if isinstance(func, CustomFunctionDef) and not func.has_signature:
            func_ty = FunctionType(
                [FuncInput(get_type(arg), InputFlags.NoFlags) for arg in node.args],
                get_type(node),
            )
        else:
            func_ty = func.ty.instantiate(node.type_args)
        self._visit_call_args(func_ty, node)
        self._reassign_inout_args(func_ty, node)

    def visit_LocalCall(self, node: LocalCall) -> None:
        func_ty = get_type(node.func)
        assert isinstance(func_ty, FunctionType)
        self.visit(node.func)
        self._visit_call_args(func_ty, node)
        self._reassign_inout_args(func_ty, node)

    def visit_TensorCall(self, node: TensorCall) -> None:
        for arg in node.args:
            self.visit(arg)
        self._reassign_inout_args(node.tensor_ty, node)

    def visit_PartialApply(self, node: PartialApply) -> None:
        self.visit(node.func)
        for arg in node.args:
            ty = get_type(arg)
            if ty.linear:
                err = LinearPartialApplyError(node)
                err.add_sub_diagnostic(LinearPartialApplyError.Captured(arg, ty))
                raise GuppyError(err)
            self.visit(arg)

    def visit_FieldAccessAndDrop(self, node: FieldAccessAndDrop) -> None:
        # A field access on a value that is not a place. This means the value can no
        # longer be accessed after the field has been projected out. Thus, this is only
        # legal if there are no remaining linear fields on the value
        self.visit(node.value)
        for field in node.struct_ty.fields:
            if field.name != node.field.name and field.ty.linear:
                err = UnnamedFieldNotUsedError(node.value, field, node.struct_ty)
                err.add_sub_diagnostic(UnnamedFieldNotUsedError.Fix(None, node.field))
                raise GuppyError(err)

    def visit_SubscriptAccessAndDrop(self, node: SubscriptAccessAndDrop) -> None:
        # A subscript access on a value that is not a place. This means the value can no
        # longer be accessed after the item has been projected out. Thus, this is only
        # legal if the items in the container are not linear
        elem_ty = get_type(node.getitem_expr)
        if elem_ty.linear:
            value = node.original_expr.value
            err = UnnamedSubscriptNotUsedError(value, get_type(value))
            err.add_sub_diagnostic(
                UnnamedSubscriptNotUsedError.SubscriptHint(node.item_expr)
            )
            err.add_sub_diagnostic(UnnamedSubscriptNotUsedError.Fix(None))
            raise GuppyTypeError(err)
        self.visit(node.item_expr)
        self.scope.assign(node.item)
        self.visit(node.getitem_expr)

    def visit_Expr(self, node: ast.Expr) -> None:
        # An expression statement where the return value is discarded
        self.visit(node.value)
        ty = get_type(node.value)
        if ty.linear:
            err = UnnamedExprNotUsedError(node, ty)
            err.add_sub_diagnostic(UnnamedExprNotUsedError.Fix(None))
            raise GuppyTypeError(err)

    def visit_DesugaredListComp(self, node: DesugaredListComp) -> None:
        self._check_comprehension(node.generators, node.elt)

    def visit_DesugaredArrayComp(self, node: DesugaredArrayComp) -> None:
        self._check_comprehension([node.generator], node.elt)

    def visit_CheckedNestedFunctionDef(self, node: CheckedNestedFunctionDef) -> None:
        # Linearity of the nested function has already been checked. We just need to
        # verify that no linear variables are captured
        # TODO: In the future, we could support capturing of non-linear subplaces
        for var, use in node.captured.values():
            if var.ty.linear:
                err = LinearCaptureError(use, var)
                err.add_sub_diagnostic(LinearCaptureError.DefinedHere(var.defined_at))
                raise GuppyError(err)
            for place in leaf_places(var):
                self.scope.use(place.id, use, UseKind.COPY)
        self.scope.assign(Variable(node.name, node.ty, node))

    def _check_assign_targets(self, targets: list[ast.expr]) -> None:
        """Helper function to check assignments."""
        # We're not allowed to override an unused linear place
        [target] = targets
        for tgt in find_nodes(lambda n: isinstance(n, PlaceNode), target):
            assert isinstance(tgt, PlaceNode)
            # Special error message for shadowing of borrowed vars
            x = tgt.place.id
            if x in self.scope.vars and is_inout_var(self.scope[x]):
                err: Error = BorrowShadowedError(tgt, tgt.place)
                err.add_sub_diagnostic(BorrowShadowedError.Rename(None))
                raise GuppyError(err)
            for tgt_place in leaf_places(tgt.place):
                x = tgt_place.id
                # Only check for overrides of places locally defined in this BB. Global
                # checks are handled by dataflow analysis.
                if x in self.scope.vars and x not in self.scope.used_local:
                    place = self.scope[x]
                    if place.ty.linear:
                        err = PlaceNotUsedError(place.defined_at, place)
                        err.add_sub_diagnostic(PlaceNotUsedError.Fix(None))
                        raise GuppyError(err)
                self.scope.assign(tgt_place)

    def _check_comprehension(
        self, gens: list[DesugaredGenerator], elt: ast.expr
    ) -> None:
        """Helper function to recursively check list comprehensions."""
        if not gens:
            self.visit(elt)
            return

        # Check the iterator expression in the current scope
        gen, *gens = gens
        self.visit(gen.iter_assign.value)
        assert isinstance(gen.iter, PlaceNode)

        # The rest is checked in a new nested scope so we can track which variables
        # are introduced and used inside the loop
        with self.new_scope() as inner_scope:
            # In particular, assign the iterator variable in the new scope
            self._check_assign_targets(gen.iter_assign.targets)
            self.visit(gen.hasnext_assign)
            self.visit(gen.next_assign)

            # `if` guards are generally not allowed when we're iterating over linear
            # variables. The only exception is if all linear variables are already
            # consumed by the first guard
            if gen.ifs:
                first_if, *other_ifs = gen.ifs
                # Check if there are linear iteration variables that have not been used
                # by the first guard
                self.visit(first_if)
                for place in self.scope.vars.values():
                    # The only exception is the iterator variable since we make sure
                    # that it is carried through each iteration during Hugr generation
                    if place == gen.iter.place:
                        continue
                    for leaf in leaf_places(place):
                        x = leaf.id
                        # Also ignore borrowed variables
                        if x in inner_scope.used_parent and (
                            inner_scope.used_parent[x].kind == UseKind.BORROW
                        ):
                            continue
                        if not self.scope.used(x) and place.ty.linear:
                            err = PlaceNotUsedError(place.defined_at, place)
                            err.add_sub_diagnostic(
                                PlaceNotUsedError.Branch(first_if, False)
                            )
                            raise GuppyTypeError(err)
                for expr in other_ifs:
                    self.visit(expr)

            # Recursively check the remaining generators
            self._check_comprehension(gens, elt)

            # Look for any linear variables that were borrowed from the outer scope
            gen.borrowed_outer_places = []
            for x, use in inner_scope.used_parent.items():
                if use.kind == UseKind.BORROW:
                    # Since `x` was borrowed, we know that is now also assigned in the
                    # inner scope since it gets reassigned in the local scope after the
                    # borrow expires
                    place = inner_scope[x]
                    gen.borrowed_outer_places.append(place)
                    # Also mark this place as implicitly used so we don't complain about
                    # it later.
                    for leaf in leaf_places(place):
                        inner_scope.use(
                            leaf.id, InoutReturnSentinel(leaf), UseKind.RETURN
                        )

            # Check the iter finalizer so we record a final use of the iterator
            self.visit(gen.iterend)

            # We have to make sure that all linear variables that were introduced in the
            # inner scope have been used
            for place in inner_scope.vars.values():
                for leaf in leaf_places(place):
                    x = leaf.id
                    if leaf.ty.linear and not inner_scope.used(x):
                        raise GuppyTypeError(PlaceNotUsedError(leaf.defined_at, leaf))

        # On the other hand, we have to ensure that no linear places from the
        # outer scope have been used inside the comprehension (they would be used
        # multiple times since the comprehension body is executed repeatedly)
        for x, use in inner_scope.used_parent.items():
            place = inner_scope[x]
            # The only exception are values that are only borrowed from the outer
            # scope. These can be safely reassigned.
            if use.kind == UseKind.BORROW:
                self._reassign_single_inout_arg(place, use.node)
            elif place.ty.linear:
                raise GuppyTypeError(ComprAlreadyUsedError(use.node, place, use.kind))


def leaf_places(place: Place) -> Iterator[Place]:
    """Returns all leaf descendant projections of a place."""
    stack = [place]
    while stack:
        place = stack.pop()
        if isinstance(place.ty, StructType):
            stack += [
                FieldAccess(place, field, place.defined_at) for field in place.ty.fields
            ]
        else:
            yield place


def contains_subscript(place: Place) -> SubscriptAccess | None:
    """Checks if a place contains a subscript access and returns the rightmost one."""
    while not isinstance(place, Variable):
        if isinstance(place, SubscriptAccess):
            return place
        place = place.parent
    return None


def is_inout_var(place: Place) -> TypeGuard[Variable]:
    """Checks whether a place is a borrowed variable."""
    return isinstance(place, Variable) and InputFlags.Inout in place.flags


def check_cfg_linearity(
    cfg: "CheckedCFG[Variable]", func_name: str, globals: Globals
) -> "CheckedCFG[Place]":
    """Checks whether a CFG satisfies the linearity requirements.

    Raises a user-error if linearity violations are found.

    Returns a new CFG with refined basic block signatures in terms of *places* rather
    than just variables.
    """
    bb_checker = BBLinearityChecker()
    func_inputs: dict[PlaceId, Variable] = {v.id: v for v in cfg.entry_bb.sig.input_row}
    scopes: dict[BB, Scope] = {
        bb: bb_checker.check(
            bb,
            is_entry=bb == cfg.entry_bb,
            func_name=func_name,
            func_inputs=func_inputs,
            globals=globals,
        )
        for bb in cfg.bbs
    }

    # Mark the borrowed variables as implicitly used in the exit BB
    exit_scope = scopes[cfg.exit_bb]
    for var in cfg.entry_bb.sig.input_row:
        if InputFlags.Inout in var.flags:
            for leaf in leaf_places(var):
                exit_scope.use(leaf.id, InoutReturnSentinel(var=var), UseKind.RETURN)

    # Edge case: If the exit is unreachable, then the function will never terminate, so
    # there is no need to give the borrowed values back to the caller. To ensure that
    # the generated Hugr is still valid, we have to thread the borrowed arguments
    # through the non-terminating loop. We achieve this by considering borrowed
    # variables as live in every BB, even if the actual use in the exit is unreachable.
    # This is done by including borrowed vars in the initial value for the liveness
    # analysis below. The analogous thing was also done in the previous `CFG.analyze`
    # pass.
    live_default: LivenessDomain[PlaceId] = (
        {
            leaf.id: cfg.exit_bb
            for var in cfg.entry_bb.sig.input_row
            if InputFlags.Inout in var.flags
            for leaf in leaf_places(var)
        }
        if not cfg.exit_bb.reachable
        else {}
    )

    # Run liveness analysis with this initial value
    stats = {bb: scope.stats() for bb, scope in scopes.items()}
    live_before = LivenessAnalysis(
        stats, initial=live_default, include_unreachable=False
    ).run(cfg.bbs)

    # Construct a CFG that tracks places instead of just variables
    result_cfg: CheckedCFG[Place] = CheckedCFG(cfg.input_tys, cfg.output_ty)
    checked: dict[BB, CheckedBB[Place]] = {}

    for bb, scope in scopes.items():
        live_before_bb = live_before[bb]

        # We have to check that used linear variables are not being outputted
        for succ in bb.successors:
            live = live_before[succ]
            for x, use_bb in live.items():
                use_scope = scopes[use_bb]
                place = use_scope[x]
                if place.ty.linear and (prev_use := scope.used(x)):
                    use = use_scope.used_parent[x]
                    # Special case if this is a use arising from the implicit returning
                    # of a borrowed argument
                    if isinstance(use.node, InoutReturnSentinel):
                        assert isinstance(use.node.var, Variable)
                        assert InputFlags.Inout in use.node.var.flags
                        err: Error = BorrowSubPlaceUsedError(
                            use.node.var.defined_at, use.node.var, place
                        )
                        err.add_sub_diagnostic(
                            BorrowSubPlaceUsedError.PrevUse(
                                prev_use.node, prev_use.kind
                            )
                        )
                        err.add_sub_diagnostic(BorrowSubPlaceUsedError.Fix(None))
                        raise GuppyError(err)
                    err = AlreadyUsedError(use.node, place, use.kind)
                    err.add_sub_diagnostic(
                        AlreadyUsedError.PrevUse(prev_use.node, prev_use.kind)
                    )
                    raise GuppyError(err)

        # On the other hand, unused linear variables *must* be outputted
        for place in scope.values():
            for leaf in leaf_places(place):
                x = leaf.id
                # Some values are just in scope because the type checker determined
                # them as live in the first (less precises) dataflow analysis. It
                # might be the case that x is actually not live when considering
                # the second, more fine-grained, analysis based on places.
                if x not in live_before_bb and x not in scope.vars:
                    continue
                used_later = all(x in live_before[succ] for succ in bb.successors)
                if leaf.ty.linear and not scope.used(x) and not used_later:
                    err = PlaceNotUsedError(scope[x].defined_at, leaf)
                    # If there are some paths that lead to a consumption, we can give
                    # a nicer error message by highlighting the branch that leads to
                    # the leak
                    if any(x in live_before[succ] for succ in bb.successors):
                        assert bb.branch_pred is not None
                        [left_succ, _] = bb.successors
                        err.add_sub_diagnostic(
                            PlaceNotUsedError.Branch(
                                bb.branch_pred, x in live_before[left_succ]
                            )
                        )
                    err.add_sub_diagnostic(PlaceNotUsedError.Fix(None))
                    raise GuppyError(err)

        def live_places_row(bb: BB, original_row: Row[Variable]) -> Row[Place]:
            """Construct a row of all places that are live at the start of a given BB.

            The only exception are input and exit BBs whose signature should not be
            split up into places but instead keep the original variable signature.
            """
            if bb in (cfg.entry_bb, cfg.exit_bb):
                return original_row
            # N.B. we can ignore lint B023. The use of loop variable `scope` below is
            # safe since we don't call this function outside the loop.
            return [scope[x] for x in live_before[bb]]  # noqa: B023

        assert isinstance(bb, CheckedBB)
        sig = Signature(
            input_row=live_places_row(bb, bb.sig.input_row),
            output_rows=[
                live_places_row(succ, output_row)
                for succ, output_row in zip(
                    bb.successors, bb.sig.output_rows, strict=True
                )
            ],
        )
        checked[bb] = CheckedBB(
            bb.idx,
            result_cfg,
            bb.statements,
            branch_pred=bb.branch_pred,
            reachable=bb.reachable,
            sig=sig,
        )

    # Fill in missing fields of the result CFG
    result_cfg.bbs = list(checked.values())
    result_cfg.entry_bb = checked[cfg.entry_bb]
    result_cfg.exit_bb = checked[cfg.exit_bb]
    result_cfg.live_before = {checked[bb]: cfg.live_before[bb] for bb in cfg.bbs}
    result_cfg.ass_before = {checked[bb]: cfg.ass_before[bb] for bb in cfg.bbs}
    result_cfg.maybe_ass_before = {
        checked[bb]: cfg.maybe_ass_before[bb] for bb in cfg.bbs
    }
    for bb in cfg.bbs:
        checked[bb].predecessors = [checked[pred] for pred in bb.predecessors]
        checked[bb].successors = [checked[succ] for succ in bb.successors]
    return result_cfg
