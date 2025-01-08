import ast
import inspect
from collections.abc import Callable, KeysView, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, TypeVar, cast, overload

from hugr import ops
from hugr import tys as ht
from hugr import val as hv
from hugr.package import FuncDefnPointer, ModulePointer

import guppylang
from guppylang.ast_util import annotate_location
from guppylang.definition.common import DefId
from guppylang.definition.const import RawConstDef
from guppylang.definition.custom import (
    CustomCallChecker,
    CustomInoutCallCompiler,
    DefaultCallChecker,
    NotImplementedCallCompiler,
    OpCompiler,
    RawCustomFunctionDef,
)
from guppylang.definition.extern import RawExternDef
from guppylang.definition.function import (
    CompiledFunctionDef,
    RawFunctionDef,
)
from guppylang.definition.parameter import ConstVarDef, TypeVarDef
from guppylang.definition.pytket_circuits import RawLoadPytketDef
from guppylang.definition.struct import RawStructDef
from guppylang.definition.traced import RawTracedFunctionDef
from guppylang.definition.ty import OpaqueTypeDef, TypeDef
from guppylang.error import MissingModuleError, pretty_errors
from guppylang.ipython_inspect import (
    get_ipython_globals,
    is_ipython_dummy_file,
    is_running_ipython,
)
from guppylang.module import (
    GuppyModule,
    PyClass,
    PyFunc,
    find_guppy_module_in_py_module,
    get_calling_frame,
    sphinx_running,
)
from guppylang.span import Loc, SourceMap, Span
from guppylang.tracing.object import GuppyDefinition
from guppylang.tys.arg import Argument
from guppylang.tys.param import Parameter
from guppylang.tys.subst import Inst
from guppylang.tys.ty import NumericType

S = TypeVar("S")
T = TypeVar("T")
Decorator = Callable[[S], T]

FuncDecorator = Decorator[PyFunc, GuppyDefinition]
ClassDecorator = Decorator[PyClass, GuppyDefinition]


_JUPYTER_NOTEBOOK_MODULE = "<jupyter-notebook>"


@dataclass(frozen=True)
class ModuleIdentifier:
    """Identifier for the Python file/module that called the decorator."""

    filename: Path

    #: The name of the module. We only store this to have nice name to report back to
    #: the user. When determining whether two `ModuleIdentifier`s correspond to the same
    #: module, we only take the module path into account.
    name: str = field(compare=False)

    #: A reference to the python module
    module: ModuleType | None = field(compare=False)


class _Guppy:
    """Class for the `@guppy` decorator."""

    # The currently-alive GuppyModules, associated with a Python file/module
    _modules: dict[ModuleIdentifier, GuppyModule]

    # Storage for source code that has been read by the compiler
    _sources: SourceMap

    def __init__(self) -> None:
        self._modules = {}
        self._sources = SourceMap()

    @overload
    def __call__(self, arg: PyFunc) -> GuppyDefinition: ...

    @overload
    def __call__(self, arg: GuppyModule) -> FuncDecorator: ...

    @pretty_errors
    def __call__(self, arg: PyFunc | GuppyModule) -> FuncDecorator | GuppyDefinition:
        """Decorator to annotate Python functions as Guppy code.

        Optionally, the `GuppyModule` in which the function should be placed can
        be passed to the decorator.
        """

        def dec(f: Callable[..., Any], module: GuppyModule) -> GuppyDefinition:
            defn = module.register_func_def(f)
            return GuppyDefinition(defn)

        return self._with_optional_module(dec, arg)

    @overload  # Always S != GuppyModule, hence ok to:
    def _with_optional_module(  # type: ignore[overload-overlap]
        self, dec: Callable[[S, GuppyModule], T], arg: S
    ) -> T: ...

    @overload
    def _with_optional_module(
        self, dec: Callable[[S, GuppyModule], T], arg: GuppyModule
    ) -> Decorator[S, T]: ...

    def _with_optional_module(
        self, dec: Callable[[S, GuppyModule], T], arg: S | GuppyModule
    ) -> Decorator[S, T] | T:
        """Helper function to define decorators that take an optional `GuppyModule`
        argument but no other arguments.

        For example, we allow `@guppy(module)` but also `@guppy`.
        """
        if isinstance(arg, GuppyModule):
            return lambda s: dec(s, arg)
        return dec(arg, self.get_module())

    def _get_python_caller(self, fn: PyFunc | None = None) -> ModuleIdentifier:
        """Returns an identifier for the Python file/module that called the decorator.

        :param fn: Optional. The function that was decorated.
        """
        if fn is not None:
            filename = inspect.getfile(fn)
            module = inspect.getmodule(fn)
        else:
            frame = inspect.currentframe()
            # loop to skip frames from the `pretty_error` decorator
            while frame:
                info = inspect.getframeinfo(frame)
                if info and info.filename != __file__:
                    module = inspect.getmodule(frame)
                    if module != guppylang.error:
                        break
                frame = frame.f_back
            else:
                raise RuntimeError("Could not find a caller for the `@guppy` decorator")

            # Jupyter notebook cells all get different dummy filenames. However,
            # we want the whole notebook to correspond to a single implicit
            # Guppy module.
            filename = info.filename
            if is_running_ipython() and not module and is_ipython_dummy_file(filename):
                filename = _JUPYTER_NOTEBOOK_MODULE
        module_path = Path(filename)
        return ModuleIdentifier(
            module_path, module.__name__ if module else module_path.name, module
        )

    @pretty_errors
    def traced(self, arg: PyFunc | GuppyModule) -> FuncDecorator | GuppyDefinition:
        def dec(f: Callable[..., Any], module: GuppyModule) -> GuppyDefinition:
            defn = RawTracedFunctionDef(DefId.fresh(module), f.__name__, None, f, {})
            module.register_def(defn)
            return GuppyDefinition(defn)

        return self._with_optional_module(dec, arg)

    def init_module(self, import_builtins: bool = True) -> None:
        """Manually initialises a Guppy module for the current Python file.

        Calling this method is only required when trying to define an empty module or
        a module that doesn't include the builtins.
        """
        module_id = self._get_python_caller()
        if module_id in self._modules:
            msg = f"Module {module_id.name} is already initialised"
            raise ValueError(msg)
        self._modules[module_id] = GuppyModule(module_id.name, import_builtins)

    @pretty_errors
    def extend_type(
        self, defn: TypeDef, module: GuppyModule | None = None
    ) -> Callable[[type], type]:
        """Decorator to add new instance functions to a type."""
        mod = module or self.get_module()
        mod._instance_func_buffer = {}

        def dec(c: type) -> type:
            mod._register_buffered_instance_funcs(defn)
            return c

        return dec

    @pretty_errors
    def type(
        self,
        hugr_ty: ht.Type | Callable[[Sequence[Argument]], ht.Type],
        name: str = "",
        linear: bool = False,
        bound: ht.TypeBound | None = None,
        params: Sequence[Parameter] | None = None,
        module: GuppyModule | None = None,
    ) -> ClassDecorator:
        """Decorator to annotate a class definitions as Guppy types.

        Requires the static Hugr translation of the type. Additionally, the type can be
        marked as linear. All `@guppy` annotated functions on the class are turned into
        instance functions.

        For non-generic types, the Hugr representation can be passed as a static value.
        For generic types, a callable may be passed that takes the type arguments of a
        concrete instantiation.
        """
        mod = module or self.get_module()
        mod._instance_func_buffer = {}

        mk_hugr_ty = (lambda _: hugr_ty) if isinstance(hugr_ty, ht.Type) else hugr_ty

        def dec(c: type) -> GuppyDefinition:
            defn = OpaqueTypeDef(
                DefId.fresh(mod),
                name or c.__name__,
                None,
                params or [],
                linear,
                mk_hugr_ty,
                bound,
            )
            mod.register_def(defn)
            mod._register_buffered_instance_funcs(defn)
            return GuppyDefinition(defn)

        return dec

    @property
    def struct(
        self,
    ) -> Callable[[PyClass | GuppyModule], ClassDecorator | GuppyDefinition]:
        """Decorator to define a new struct."""
        # Note that this is a property. Thus, the code below is executed *before*
        # the members of the decorated class are executed.
        # At this point, we don't know if the user has called `@struct(module)` or
        # just `@struct`. To be safe, we initialise the method buffer of the implicit
        # module either way
        caller_id = self._get_python_caller()
        implicit_module_existed = caller_id in self._modules
        implicit_module = self.get_module(
            # But don't try to do implicit imports since we're not sure if this is
            # actually an implicit module
            resolve_implicit_imports=False
        )
        implicit_module._instance_func_buffer = {}

        # Extract Python scope from the frame that called `guppy.struct`
        frame = get_calling_frame()
        python_scope = frame.f_globals | frame.f_locals if frame else {}

        def dec(cls: type, module: GuppyModule) -> GuppyDefinition:
            defn = RawStructDef(
                DefId.fresh(module), cls.__name__, None, cls, python_scope
            )
            module.register_def(defn)
            module._register_buffered_instance_funcs(defn)
            # If we mistakenly initialised the method buffer of the implicit module
            # we can just clear it here
            if module != implicit_module:
                assert implicit_module._instance_func_buffer == {}
                implicit_module._instance_func_buffer = None
                if not implicit_module_existed:
                    self._modules.pop(caller_id)
            return GuppyDefinition(defn)

        def higher_dec(arg: GuppyModule | PyClass) -> ClassDecorator | GuppyDefinition:
            if isinstance(arg, GuppyModule):
                arg._instance_func_buffer = {}
            return self._with_optional_module(dec, arg)

        return higher_dec

    @pretty_errors
    def type_var(
        self, name: str, linear: bool = False, module: GuppyModule | None = None
    ) -> TypeVar:
        """Creates a new type variable in a module."""
        module = module or self.get_module()
        defn = TypeVarDef(DefId.fresh(module), name, None, linear)
        module.register_def(defn)
        # Return an actual Python `TypeVar` so it can be used as an actual type in code
        # that is executed by interpreter before handing it to Guppy.
        return TypeVar(name)

    @pretty_errors
    def nat_var(self, name: str, module: GuppyModule | None = None) -> TypeVar:
        """Creates a new const nat variable in a module."""
        module = module or self.get_module()
        defn = ConstVarDef(
            DefId.fresh(module), name, None, NumericType(NumericType.Kind.Nat)
        )
        module.register_def(defn)
        # Return an actual Python `TypeVar` so it can be used as an actual type in code
        # that is executed by interpreter before handing it to Guppy.
        return TypeVar(name)

    @pretty_errors
    def custom(
        self,
        compiler: CustomInoutCallCompiler | None = None,
        checker: CustomCallChecker | None = None,
        higher_order_value: bool = True,
        name: str = "",
        module: GuppyModule | None = None,
    ) -> FuncDecorator:
        """Decorator to add custom typing or compilation behaviour to function decls.

        Optionally, usage of the function as a higher-order value can be disabled. In
        that case, the function signature can be omitted if a custom call compiler is
        provided.
        """
        mod = module or self.get_module()

        def dec(f: PyFunc) -> GuppyDefinition:
            call_checker = checker or DefaultCallChecker()
            func = RawCustomFunctionDef(
                DefId.fresh(mod),
                name or f.__name__,
                None,
                f,
                call_checker,
                compiler or NotImplementedCallCompiler(),
                higher_order_value,
            )
            mod.register_def(func)
            return GuppyDefinition(func)

        return dec

    def hugr_op(
        self,
        op: Callable[[ht.FunctionType, Inst], ops.DataflowOp],
        checker: CustomCallChecker | None = None,
        higher_order_value: bool = True,
        name: str = "",
        module: GuppyModule | None = None,
    ) -> FuncDecorator:
        """Decorator to annotate function declarations as HUGR ops.

        Args:
            module: The module in which the function should be defined.
            op: A function that takes an instantiation of the type arguments as well as
                the inferred input and output types and returns a concrete HUGR op.
            checker: The custom call checker.
            higher_order_value: Whether the function may be used as a higher-order
                value.
            name: The name of the function.
        """
        return self.custom(OpCompiler(op), checker, higher_order_value, name, module)

    @overload
    def declare(self, arg: GuppyModule) -> GuppyDefinition: ...

    @overload
    def declare(self, arg: PyFunc) -> FuncDecorator: ...

    def declare(self, arg: GuppyModule | PyFunc) -> FuncDecorator | GuppyDefinition:
        """Decorator to declare functions"""

        def dec(f: Callable[..., Any], module: GuppyModule) -> GuppyDefinition:
            defn = module.register_func_decl(f)
            return GuppyDefinition(defn)

        return self._with_optional_module(dec, arg)

    def constant(
        self, name: str, ty: str, value: hv.Value, module: GuppyModule | None = None
    ) -> GuppyDefinition:
        """Adds a constant to a module, backed by a `hugr.val.Value`."""
        module = module or self.get_module()
        type_ast = _parse_expr_string(
            ty, f"Not a valid Guppy type: `{ty}`", self._sources
        )
        defn = RawConstDef(DefId.fresh(module), name, None, type_ast, value)
        module.register_def(defn)
        return GuppyDefinition(defn)

    def extern(
        self,
        name: str,
        ty: str,
        symbol: str | None = None,
        constant: bool = True,
        module: GuppyModule | None = None,
    ) -> GuppyDefinition:
        """Adds an extern symbol to a module."""
        module = module or self.get_module()
        type_ast = _parse_expr_string(
            ty, f"Not a valid Guppy type: `{ty}`", self._sources
        )
        defn = RawExternDef(
            DefId.fresh(module), name, None, symbol or name, constant, type_ast
        )
        module.register_def(defn)
        return GuppyDefinition(defn)

    def load(self, m: ModuleType | GuppyModule) -> None:
        caller = self._get_python_caller()
        if caller not in self._modules:
            self._modules[caller] = GuppyModule(caller.name)
        module = self._modules[caller]
        module.load_all(m)

    def get_module(
        self, id: ModuleIdentifier | None = None, resolve_implicit_imports: bool = True
    ) -> GuppyModule:
        """Returns the local GuppyModule."""
        if id is None:
            id = self._get_python_caller()
        if id not in self._modules:
            self._modules[id] = GuppyModule(id.name.split(".")[-1])
        module = self._modules[id]
        # Update implicit imports
        if resolve_implicit_imports:
            globs: dict[str, Any] = {}
            if id.module:
                globs = id.module.__dict__
            # Jupyter notebooks are not made up of a single module, so we need to find
            # it's globals by querying the ipython kernel
            elif id.name == _JUPYTER_NOTEBOOK_MODULE:
                globs = get_ipython_globals()
            if globs:
                defs: dict[str, GuppyDefinition | ModuleType] = {}
                for x, value in globs.items():
                    if isinstance(value, GuppyDefinition):
                        other_module = value.wrapped.id.module
                        if other_module and other_module != module:
                            defs[x] = value
                    elif isinstance(value, ModuleType):
                        try:
                            other_module = find_guppy_module_in_py_module(value)
                            if other_module and other_module != module:
                                defs[x] = value
                        except ValueError:
                            pass
                module.load(**defs)
        return module

    def compile_module(self, id: ModuleIdentifier | None = None) -> ModulePointer:
        """Compiles the xlocal module into a Hugr."""
        module = self.get_module(id)
        if not module:
            err = (
                f"Module {id.name} not found."
                if id
                else "No Guppy functions or types defined in this module."
            )
            raise MissingModuleError(err)
        return module.compile()

    def compile_function(
        self, f_def: RawFunctionDef | RawTracedFunctionDef
    ) -> FuncDefnPointer:
        """Compiles a single function definition."""
        module = f_def.id.module
        if not module:
            raise ValueError("Function definition must belong to a module")
        compiled_module = module.compile()
        assert module._compiled is not None, "Module should be compiled"
        globs = module._compiled.globs
        assert globs is not None
        compiled_def = globs.build_compiled_def(f_def.id)
        assert isinstance(compiled_def, CompiledFunctionDef)
        node = compiled_def.func_def.parent_node
        return FuncDefnPointer(
            compiled_module.package, compiled_module.module_index, node
        )

    def registered_modules(self) -> KeysView[ModuleIdentifier]:
        """Returns a list of all currently registered modules for local contexts."""
        return self._modules.keys()

    @pretty_errors
    def pytket(
        self, input_circuit: Any, module: GuppyModule | None = None
    ) -> FuncDecorator:
        """Adds a pytket circuit function definition with explicit signature."""
        err_msg = "Only pytket circuits can be passed to guppy.pytket"
        try:
            import pytket

            if not isinstance(input_circuit, pytket.circuit.Circuit):
                raise TypeError(err_msg) from None

        except ImportError:
            raise TypeError(err_msg) from None

        mod = module or self.get_module()

        def func(f: PyFunc) -> GuppyDefinition:
            defn = mod.register_pytket_func(f, input_circuit)
            return GuppyDefinition(defn)

        return func

    @pretty_errors
    def load_pytket(
        self, name: str, input_circuit: Any, module: GuppyModule | None = None
    ) -> GuppyDefinition:
        """Adds a pytket circuit function definition with implicit signature."""
        err_msg = "Only pytket circuits can be passed to guppy.load_pytket"
        try:
            import pytket

            if not isinstance(input_circuit, pytket.circuit.Circuit):
                raise TypeError(err_msg) from None

        except ImportError:
            raise TypeError(err_msg) from None

        mod = module or self.get_module()
        span = _find_load_call(self._sources)
        defn = RawLoadPytketDef(DefId.fresh(module), name, None, span, input_circuit)
        mod.register_def(defn)
        return GuppyDefinition(defn)


class _GuppyDummy:
    """A dummy class with the same interface as `@guppy` that is used during sphinx
    builds to mock the decorator.
    """

    _sources = SourceMap()

    def __call__(self, arg: PyFunc | GuppyModule) -> Any:
        if isinstance(arg, GuppyModule):
            return lambda f: f
        return arg

    def init_module(self, *args: Any, **kwargs: Any) -> None:
        pass

    def extend_type(self, *args: Any, **kwargs: Any) -> Any:
        return lambda cls: cls

    def type(self, *args: Any, **kwargs: Any) -> Any:
        return lambda cls: cls

    def struct(self, *args: Any, **kwargs: Any) -> Any:
        return lambda cls: cls

    def type_var(self, name: str, *args: Any, **kwargs: Any) -> Any:
        # Return an actual type variable so it can be used in `Generic[...]`
        return TypeVar(name)

    def nat_var(self, name: str, *args: Any, **kwargs: Any) -> Any:
        # Return an actual type variable so it can be used in `Generic[...]`
        return TypeVar(name)

    def custom(self, *args: Any, **kwargs: Any) -> Any:
        return lambda f: f

    def hugr_op(self, *args: Any, **kwargs: Any) -> Any:
        return lambda f: f

    def declare(self, arg: PyFunc | GuppyModule) -> Any:
        if isinstance(arg, GuppyModule):
            return lambda f: f
        return arg

    def constant(self, *args: Any, **kwargs: Any) -> Any:
        return None

    def extern(self, *args: Any, **kwargs: Any) -> Any:
        return None

    def load(self, *args: Any, **kwargs: Any) -> None:
        pass


guppy = cast(_Guppy, _GuppyDummy()) if sphinx_running() else _Guppy()


def _parse_expr_string(ty_str: str, parse_err: str, sources: SourceMap) -> ast.expr:
    """Helper function to parse expressions that are provided as strings.

    Tries to infer the source location were the given string was defined by inspecting
    the call stack.
    """
    try:
        expr_ast = ast.parse(ty_str, mode="eval").body
    except SyntaxError:
        raise SyntaxError(parse_err) from None

    # Try to annotate the type AST with source information. This requires us to
    # inspect the stack frame of the caller
    if caller_frame := get_calling_frame():
        info = inspect.getframeinfo(caller_frame)
        if caller_module := inspect.getmodule(caller_frame):
            sources.add_file(info.filename)
            source_lines, _ = inspect.getsourcelines(caller_module)
            source = "".join(source_lines)
            annotate_location(expr_ast, source, info.filename, 1)
            # Modify the AST so that all sub-nodes span the entire line. We
            # can't give a better location since we don't know the column
            # offset of the `ty` argument
            for node in [expr_ast, *ast.walk(expr_ast)]:
                node.lineno = node.end_lineno = info.lineno
                node.col_offset = 0
                node.end_col_offset = len(source_lines[info.lineno - 1]) - 1
    return expr_ast


def _find_load_call(sources: SourceMap) -> Span | None:
    """Helper function to find location where pytket circuit was loaded.

    Tries to define a source code span by inspecting the call stack.
    """
    # Go back as first frame outside of compiler modules is 'pretty_errors_wrapped'.
    if (caller_frame := get_calling_frame()) and (load_frame := caller_frame.f_back):
        info = inspect.getframeinfo(load_frame)
        filename = info.filename
        lineno = info.lineno
        sources.add_file(filename)
        # If we don't support python <= 3.10, this can be done better with
        # info.positions which gives you exact offsets.
        # For now over approximate and make the span cover the entire line.
        if load_module := inspect.getmodule(load_frame):
            source_lines, _ = inspect.getsourcelines(load_module)
            max_offset = len(source_lines[lineno - 1]) - 1

            start = Loc(filename, lineno, 0)
            end = Loc(filename, lineno, max_offset)
            return Span(start, end)
    return None
