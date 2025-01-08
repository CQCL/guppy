import inspect
import itertools
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, NamedTuple

from hugr import Wire, ops

from guppylang.definition.common import DefId, Definition
from guppylang.definition.function import RawFunctionDef
from guppylang.definition.ty import TypeDef
from guppylang.definition.value import CompiledCallableDef, CompiledValueDef
from guppylang.ipython_inspect import find_ipython_def, is_running_ipython
from guppylang.tracing.state import get_tracing_globals, get_tracing_state
from guppylang.tracing.util import get_calling_frame, hide_trace
from guppylang.tys.ty import TupleType, Type


class GetAttrDunders(ABC):
    @abstractmethod
    def __getattr__(self, item: Any) -> Any: ...

    def __abs__(self, other: Any) -> Any:
        return self.__getattr__("__abs__")(other)

    def __add__(self, other: Any) -> Any:
        return self.__getattr__("__add__")(other)

    def __and__(self, other: Any) -> Any:
        return self.__getattr__("__and__")(other)

    def __bool__(self: Any) -> Any:
        return self.__getattr__("__bool__")()

    def __ceil__(self: Any) -> Any:
        return self.__getattr__("__bool__")()

    def __divmod__(self, other: Any) -> Any:
        return self.__getattr__("__divmod__")(other)

    def __eq__(self, other: object) -> Any:
        return self.__getattr__("__eq__")(other)

    def __float__(self) -> Any:
        return self.__getattr__("__bool__")()

    def __floor__(self) -> Any:
        return self.__getattr__("__floor__")()

    def __floordiv__(self, other: Any) -> Any:
        return self.__getattr__("__floordiv__")(other)

    def __ge__(self, other: Any) -> Any:
        return self.__getattr__("__ge__")(other)

    def __gt__(self, other: Any) -> Any:
        return self.__getattr__("__gt__")(other)

    def __int__(self) -> Any:
        return self.__getattr__("__int__")()

    def __invert__(self) -> Any:
        return self.__getattr__("__invert__")()

    def __le__(self, other: Any) -> Any:
        return self.__getattr__("__le__")(other)

    def __lshift__(self, other: Any) -> Any:
        return self.__getattr__("__lshift__")(other)

    def __lt__(self, other: Any) -> Any:
        return self.__getattr__("__lt__")(other)

    def __mod__(self, other: Any) -> Any:
        return self.__getattr__("__mod__")(other)

    def __mul__(self, other: Any) -> Any:
        return self.__getattr__("__mul__")(other)

    def __ne__(self, other: object) -> Any:
        return self.__getattr__("__ne__")(other)

    def __neg__(self) -> Any:
        return self.__getattr__("__neg__")()

    def __or__(self, other: Any) -> Any:
        return self.__getattr__("__or__")(other)

    def __pos__(self) -> Any:
        return self.__getattr__("__pos__")()

    def __pow__(self, other: Any) -> Any:
        return self.__getattr__("__pow__")(other)

    def __sub__(self, other: Any) -> Any:
        return self.__getattr__("__sub__")(other)

    def __truediv__(self, other: Any) -> Any:
        return self.__getattr__("__truediv__")(other)

    def __trunc__(self) -> Any:
        return self.__getattr__("__trunc__")()

    def __xor__(self, other: Any) -> Any:
        return self.__getattr__("__xor__")(other)


class ObjectUse(NamedTuple):
    """Records a use of a linear `GuppyObject`."""

    module: str
    lineno: int
    called_func: CompiledCallableDef | None


ObjectId = int

fresh_id = itertools.count()


class GuppyObject(GetAttrDunders):
    """The runtime representation of abstract Guppy objects during tracing."""

    _ty: Type
    _wire: Wire
    _used: ObjectUse | None
    _id: ObjectId

    def __init__(self, ty: Type, wire: Wire, used: ObjectUse | None = None) -> None:
        self._ty = ty
        self._wire = wire
        self._used = used
        self._id = next(fresh_id)
        state = get_tracing_state()
        state.allocated_objs[self._id] = self
        if ty.linear and not self._used:
            state.unused_objs.add(self._id)

    @hide_trace
    def __getattr__(self, key: str) -> Any:  # type: ignore[misc]
        globals = get_tracing_globals()
        func = globals.get_instance_func(self._ty, key)
        if func is None:
            raise AttributeError(
                f"Expression of type `{self._ty}` has no attribute `{key}`"
            )
        return lambda *xs: GuppyDefinition(func)(self, *xs)

    @hide_trace
    def __bool__(self) -> Any:
        err = (
            "Branching on a dynamic value is not allowed during tracing. Try using "
            "a regular guppy function"
        )
        raise ValueError(err)

    @hide_trace
    def __iter__(self) -> Any:
        state = get_tracing_state()
        builder = state.dfg.builder
        if isinstance(self._ty, TupleType):
            unpack = builder.add_op(ops.UnpackTuple(), self._use_wire(None))
            return (
                GuppyObject(ty, wire)
                for ty, wire in zip(
                    self._ty.element_types, unpack.outputs(), strict=False
                )
            )
        raise TypeError(f"Expression of type `{self._ty}` is not iterable")

    def _use_wire(self, called_func: CompiledCallableDef | None) -> Wire:
        # Panic if the value has already been used
        if self._used:
            use = self._used
            err = (
                f"Value with linear type `{self._ty}` was already used\n\n"
                f"Previous use occurred in {use.module}:{use.lineno}"
            )
            if use.called_func:
                err += f" as an argument to `{use.called_func.name}`"
            raise ValueError(err)
        # Otherwise, mark it as used
        else:
            frame = get_calling_frame()
            assert frame is not None
            if is_running_ipython():
                module_name = "<In [?]>"
                if defn := find_ipython_def(frame.f_code.co_name):
                    module_name = f"<{defn.cell_name}>"
            else:
                module = inspect.getmodule(frame)
                module_name = module.__file__ if module and module.__file__ else "???"
            self._used = ObjectUse(module_name, frame.f_lineno, called_func)
            if self._ty.linear:
                state = get_tracing_state()
                state.unused_objs.remove(self._id)
        return self._wire


@dataclass(frozen=True)
class GuppyDefinition:
    """A top-level Guppy definition.

    This is the object that is returned to the users when they decorate a function or
    class. In particular, this is the version of the definition that is available during
    tracing.
    """

    wrapped: Definition

    @property
    def id(self) -> DefId:
        return self.wrapped.id

    @hide_trace
    def __call__(self, *args: Any) -> Any:
        from guppylang.tracing.function import trace_call

        state = get_tracing_state()
        defn = state.globals.build_compiled_def(self.wrapped.id)
        if isinstance(defn, CompiledCallableDef):
            return trace_call(defn, *args)
        elif isinstance(defn, TypeDef):
            globals = get_tracing_globals()
            if defn.id in globals.impls and "__new__" in globals.impls[defn.id]:
                constructor = globals.defs[globals.impls[defn.id]["__new__"]]
                return GuppyDefinition(constructor)(*args)
        err = f"{defn.description.capitalize()} `{defn.name}` is not callable"
        raise TypeError(err)

    def __getitem__(self, item: Any) -> Any:
        return self

    def to_guppy_object(self) -> GuppyObject:
        state = get_tracing_state()
        defn = state.globals.build_compiled_def(self.id)
        if isinstance(defn, CompiledValueDef):
            wire = defn.load(state.dfg, state.globals, state.node)
            return GuppyObject(defn.ty, wire, None)
        elif isinstance(defn, TypeDef):
            globals = get_tracing_globals()
            if defn.id in globals.impls and "__new__" in globals.impls[defn.id]:
                constructor = globals.defs[globals.impls[defn.id]["__new__"]]
                return GuppyDefinition(constructor).to_guppy_object()
        err = f"{defn.description.capitalize()} `{defn.name}` is not a value"
        raise TypeError(err)

    def compile(self) -> Any:
        from guppylang.decorator import guppy

        assert isinstance(self.wrapped, RawFunctionDef)
        return guppy.compile_function(self.wrapped)
