import inspect
import sys
from abc import ABC
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

ExtensionId = str
ExtensionSet = list[  # TODO: Set not supported by MessagePack. Is list correct here?
    ExtensionId
]


# --------------------------------------------
# --------------- TypeParam ------------------
# --------------------------------------------


class TypeParam(BaseModel):
    tp: Literal["Type"] = "Type"
    b: "TypeBound"


class BoundedNatParam(BaseModel):
    tp: Literal["BoundedNat"] = "BoundedNat"
    bound: int | None


class OpaqueParam(BaseModel):
    tp: Literal["Opaque"] = "Opaque"
    ty: "Opaque"


class ListParam(BaseModel):
    tp: Literal["List"] = "List"
    param: "TypeParamUnion"


class TupleParam(BaseModel):
    tp: Literal["Tuple"] = "Tuple"
    params: list["TypeParamUnion"]


TypeParamUnion = Annotated[
    TypeParam | BoundedNatParam | OpaqueParam | ListParam | TupleParam,
    Field(discriminator="tp"),
]


# ------------------------------------------
# --------------- TypeArg ------------------
# ------------------------------------------


class CustomTypeArg(BaseModel):
    typ: None  # TODO
    value: str


class TypeArg(BaseModel):
    tya: Literal["Type"] = "Type"
    ty: "SimpleType"


class BoundedNatArg(BaseModel):
    tya: Literal["BoundedNat"] = "BoundedNat"
    n: int


class OpaqueArg(BaseModel):
    tya: Literal["Opaque"] = "Opaque"
    arg: CustomTypeArg


class SequenceArg(BaseModel):
    tya: Literal["Sequence"] = "Sequence"
    args: list["TypeArgUnion"]


class ExtensionsArg(BaseModel):
    tya: Literal["Extensions"] = "Extensions"
    es: ExtensionSet


TypeArgUnion = Annotated[
    TypeArg | BoundedNatArg | OpaqueArg | SequenceArg | ExtensionsArg,
    Field(discriminator="tya"),
]


# --------------------------------------------
# --------------- Container ------------------
# --------------------------------------------


class MultiContainer(BaseModel):
    ty: "SimpleType"


class List(MultiContainer):
    """Variable sized list of types"""

    t: Literal["List"] = "List"


class Array(MultiContainer):
    """Known size array of"""

    t: Literal["Array"] = "Array"
    len: int


class Tuple(BaseModel):
    """Product type, known-size tuple over elements of type row"""

    t: Literal["Tuple"] = "Tuple"
    inner: "TypeRow"


class Sum(ABC, BaseModel):
    """Sum type, variants are tagged by their position in the type row"""

    t: Literal["Sum"] = "Sum"


class UnitSum(Sum):
    """Simple predicate where all variants are empty tuples"""

    s: Literal["Unit"] = "Unit"
    size: int


class GeneralSum(Sum):
    """General sum type that explicitly stores the types of the variants"""

    s: Literal["General"] = "General"
    row: "TypeRow"


# ----------------------------------------------
# --------------- ClassicType ------------------
# ----------------------------------------------


class Variable(BaseModel):
    """A type variable identified by a de Bruijn index."""

    t: Literal["V"] = "V"
    i: int
    b: "TypeBound"


class Int(BaseModel):
    """An arbitrary size integer."""

    t: Literal["I"] = "I"
    width: int


class F64(BaseModel):
    """A 64-bit floating point number."""

    t: Literal["F"] = "F"


class String(BaseModel):
    """An arbitrary length string."""

    t: Literal["S"] = "S"


class FunctionType(BaseModel):
    """A graph encoded as a value. It contains a concrete signature and a set of
    required resources."""

    input: "TypeRow"  # Value inputs of the function.
    output: "TypeRow"  # Value outputs of the function.
    # The extension requirements which are added by the operation
    extension_reqs: "ExtensionSet" = Field(default_factory=list)

    @classmethod
    def empty(cls) -> "FunctionType":
        return FunctionType(input=[], output=[], extension_reqs=[])


class PolyFuncType(BaseModel):
    """A graph encoded as a value. It contains a concrete signature and a set of
    required resources."""

    t: Literal["G"] = "G"

    # The declared type parameters, i.e., these must be instantiated with the same
    # number of TypeArgs before the function can be called. Note that within the body,
    # variable (DeBruijn) index 0 is element 0 of this array, i.e. the variables are
    # bound from right to left.
    params: list[TypeParamUnion]

    # Template for the function. May contain variables up to length of `params`
    body: FunctionType

    @classmethod
    def empty(cls) -> "PolyFuncType":
        return PolyFuncType(params=[], body=FunctionType.empty())


class TypeBound(Enum):
    Eq = "E"
    Copyable = "C"
    Any = "A"

    @staticmethod
    def join(*bs: "TypeBound") -> "TypeBound":
        """Computes the least upper bound for a sequence of bounds."""
        res = TypeBound.Eq
        for b in bs:
            if res == TypeBound.Eq:
                res = b
            if res == TypeBound.Copyable and b == TypeBound.Any:
                res = TypeBound.Any
        return res


class Opaque(BaseModel):
    """An opaque operation that can be downcasted by the extensions that define it."""

    t: Literal["Opaque"] = "Opaque"
    extension: ExtensionId
    id: str  # Unique identifier of the opaque type.
    args: list[TypeArgUnion]
    bound: TypeBound


# ----------------------------------------------
# --------------- LinearType -------------------
# ----------------------------------------------


class Qubit(BaseModel):
    """A qubit."""

    t: Literal["Q"] = "Q"


SimpleType = Annotated[
    Qubit
    | Variable
    | Int
    | F64
    | String
    | PolyFuncType
    | List
    | Array
    | Tuple
    | Sum
    | Opaque,
    Field(discriminator="t"),
]


# -------------------------------------------
# --------------- TypeRow -------------------
# -------------------------------------------

TypeRow = list[SimpleType]


# -------------------------------------------
# --------------- Signature -----------------
# -------------------------------------------


class Signature(BaseModel):
    """Describes the edges required to/from a node.

    This includes both the concept of "signature" in the spec, and also the target
    (value) of a call (constant).
    """

    signature: "PolyFuncType"  # The underlying signature

    # The extensions which are associated with all the inputs and carried through
    input_extensions: ExtensionSet


# Now that all classes are defined, we need to update the ForwardRefs in all type
# annotations. We use some inspect magic to find all classes defined in this file.
classes = inspect.getmembers(
    sys.modules[__name__],
    lambda member: inspect.isclass(member) and member.__module__ == __name__,
)
for _, c in classes:
    if issubclass(c, BaseModel):
        c.update_forward_refs()
