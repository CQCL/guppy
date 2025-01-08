from abc import abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from hugr import tys

from guppylang.ast_util import AstNode
from guppylang.definition.common import CompiledDef, Definition
from guppylang.tys.arg import Argument
from guppylang.tys.param import Parameter, check_all_args
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
        check_all_args(self.params, args, self.name, loc)
        return OpaqueType(args, self)
