import ast
import copy
import itertools
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, NamedTuple

from typing_extensions import assert_never

from guppylang.ast_util import AstNode, name_nodes_in_ast
from guppylang.definition.common import DefId, Definition
from guppylang.definition.ty import TypeDef
from guppylang.definition.value import CallableDef
from guppylang.tys.builtin import (
    bool_type_def,
    callable_type_def,
    float_type_def,
    int_type_def,
    linst_type_def,
    list_type_def,
    none_type_def,
    tuple_type_def,
)
from guppylang.tys.ty import (
    BoundTypeVar,
    ExistentialTypeVar,
    FunctionType,
    NoneType,
    NumericType,
    OpaqueType,
    StructType,
    SumType,
    TupleType,
    Type,
)


@dataclass
class Variable:
    """Class holding data associated with a local variable."""

    name: str
    ty: Type
    defined_at: AstNode | None
    used: AstNode | None


PyScope = dict[str, Any]


@dataclass(frozen=True)
class Globals:
    """Collection of definitions that are available on module-level.

    Stores a mapping from global ids to their definition together with a mapping of
    user names to definition id and instance implementation id.
    """

    defs: Mapping[DefId, Definition]

    names: dict[str, DefId]
    impls: dict[DefId, dict[str, DefId]]
    python_scope: PyScope

    @staticmethod
    def default() -> "Globals":
        """Generates a `Globals` instance that is populated with all core types"""
        builtins: list[Definition] = [
            callable_type_def,
            tuple_type_def,
            none_type_def,
            bool_type_def,
            int_type_def,
            float_type_def,
            list_type_def,
            linst_type_def,
        ]
        defs = {defn.id: defn for defn in builtins}
        names = {defn.name: defn.id for defn in builtins}
        return Globals(defs, names, {}, {})

    def get_instance_func(self, ty: Type | TypeDef, name: str) -> CallableDef | None:
        """Looks up an instance function with a given name for a type.

        Returns `None` if the name doesn't exist or isn't a function.
        """
        type_defn: TypeDef
        match ty:
            case TypeDef() as type_defn:
                pass
            case BoundTypeVar() | ExistentialTypeVar() | SumType():
                return None
            case NumericType(kind):
                match kind:
                    case NumericType.Kind.Bool:
                        type_defn = bool_type_def
                    case NumericType.Kind.Int:
                        type_defn = int_type_def
                    case NumericType.Kind.Float:
                        type_defn = float_type_def
                    case kind:
                        return assert_never(kind)
            case FunctionType():
                type_defn = callable_type_def
            case OpaqueType() as ty:
                type_defn = ty.defn
            case StructType() as ty:
                type_defn = ty.defn
            case TupleType():
                type_defn = tuple_type_def
            case NoneType():
                type_defn = none_type_def
            case _:
                return assert_never(ty)

        if type_defn.id in self.impls and name in self.impls[type_defn.id]:
            def_id = self.impls[type_defn.id][name]
            defn = self.defs[def_id]
            if isinstance(defn, CallableDef):
                return defn
        return None

    def update_defs(self, defs: Mapping[DefId, Definition]) -> "Globals":
        """Returns a new `Globals` instance with updated definitions.

        This method is needed since in-place definition updates are impossible as the
        definition map is immutable.
        """
        return Globals({**self.defs, **defs}, self.names, self.impls, self.python_scope)

    def __or__(self, other: "Globals") -> "Globals":
        impls = {
            def_id: self.impls.get(def_id, {}) | other.impls.get(def_id, {})
            for def_id in self.impls.keys() | other.impls.keys()
        }
        return Globals(
            {**self.defs, **other.defs},  # Can't use `|` since it's a Mapping
            self.names | other.names,
            impls,
            self.python_scope | other.python_scope,
        )

    def __contains__(self, item: DefId | str) -> bool:
        match item:
            case DefId() as def_id:
                return def_id in self.defs
            case str(name):
                return name in self.names
            case x:
                return assert_never(x)

    def __getitem__(self, item: DefId | str) -> Definition:
        match item:
            case DefId() as def_id:
                return self.defs[def_id]
            case str(name):
                return self.defs[self.names[name]]
            case x:
                return assert_never(x)


@dataclass
class Locals:
    """Scoped mapping from names to variables"""

    vars: dict[str, Variable]
    parent_scope: "Locals | None" = None

    def __getitem__(self, item: str) -> Variable:
        if item not in self.vars and self.parent_scope:
            return self.parent_scope[item]

        return self.vars[item]

    def __setitem__(self, key: str, value: Variable) -> None:
        self.vars[key] = value

    def __iter__(self) -> Iterator[str]:
        parent_iter = iter(self.parent_scope) if self.parent_scope else iter(())
        return itertools.chain(iter(self.vars), parent_iter)

    def __contains__(self, item: str) -> bool:
        return (item in self.vars) or (
            self.parent_scope is not None and item in self.parent_scope
        )

    def __copy__(self) -> "Locals":
        # Make a copy of the var map so that mutating the copy doesn't
        # mutate our variable mapping
        return Locals(self.vars.copy(), copy.copy(self.parent_scope))

    def keys(self) -> set[str]:
        parent_keys = self.parent_scope.keys() if self.parent_scope else set()
        return parent_keys | self.vars.keys()

    def items(self) -> Iterable[tuple[str, Variable]]:
        parent_items = (
            iter(self.parent_scope.items()) if self.parent_scope else iter(())
        )
        return itertools.chain(self.vars.items(), parent_items)


class Context(NamedTuple):
    """The type checking context."""

    globals: Globals
    locals: Locals


class DummyEvalDict(PyScope):
    """A custom dict that can be passed to `eval` to give better error messages.
    This class is used to implement the `py(...)` expression. If the user tries to
    access a Guppy variable in the Python context, we give an informative error message.
    """

    ctx: Context
    node: ast.expr

    @dataclass
    class GuppyVarUsedError(BaseException):
        """Error that is raised when the user tries to access a Guppy variable."""

        var: str
        node: ast.Name | None

    def __init__(self, ctx: Context, node: ast.expr):
        super().__init__(**ctx.globals.python_scope)
        self.ctx = ctx
        self.node = node

    def _check_item(self, key: str) -> None:
        # Catch the user trying to access Guppy variables
        if key in self.ctx.locals:
            # Find the name node in the AST where the usage occurs
            n = next((n for n in name_nodes_in_ast(self.node) if n.id == key), None)
            raise self.GuppyVarUsedError(key, n)

    def __getitem__(self, key: str) -> Any:
        self._check_item(key)
        return super().__getitem__(key)

    def __delitem__(self, key: str) -> None:
        self._check_item(key)
        super().__delitem__(key)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str) and key in self.ctx.locals:
            return True
        return super().__contains__(key)
