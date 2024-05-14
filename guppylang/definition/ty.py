from abc import abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from hugr.serialization import tys

from guppylang.ast_util import AstNode
from guppylang.definition.common import CompiledDef, Definition
from guppylang.error import GuppyError
from guppylang.tys.arg import Argument
from guppylang.tys.param import Parameter
from guppylang.tys.ty import OpaqueType, Type

if TYPE_CHECKING:
    from guppylang.checker.core import Globals


@dataclass(frozen=True)
class TypeDef(Definition):
    """Abstract base class for type definitions."""

    description: str = field(default="type", init=False)

    @abstractmethod
    def check_instantiate(
        self, args: Sequence[Argument], globals: "Globals", loc: AstNode | None = None
    ) -> Type:
        """Checks if the type definition can be instantiated with the given arguments.

        Returns the resulting concrete type or raises a user error if the arguments are
        invalid.
        """


@dataclass(frozen=True)
class OpaqueTypeDef(TypeDef, CompiledDef):
    """An opaque type definition that is backed by some Hugr type."""

    params: Sequence[Parameter]
    always_linear: bool
    to_hugr: Callable[[Sequence[Argument]], tys.Type]
    bound: tys.TypeBound | None = None

    def check_instantiate(
        self, args: Sequence[Argument], globals: "Globals", loc: AstNode | None = None
    ) -> OpaqueType:
        """Checks if the type definition can be instantiated with the given arguments.

        Returns the resulting concrete type or raises a user error if the arguments are
        invalid.
        """
        exp, act = len(self.params), len(args)
        if exp > act:
            raise GuppyError(f"Missing parameter for type `{self.name}`", loc)
        elif 0 == exp < act:
            raise GuppyError(f"Type `{self.name}` is not parameterized", loc)
        elif 0 < exp < act:
            raise GuppyError(f"Too many parameters for type `{self.name}`", loc)

        # Now check that the kinds match up
        for param, arg in zip(self.params, args, strict=True):
            # TODO: The error location is bad. We want the location of `arg`, not of the
            #  whole thing.
            param.check_arg(arg, loc)
        return OpaqueType(args, self)
