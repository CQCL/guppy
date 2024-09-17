import inspect
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

from hugr import Hugr, ops
from hugr.build.function import Module
from hugr.ext import Package

import guppylang.compiler.hugr_extension
from guppylang.checker.core import Globals, PyScope
from guppylang.compiler.core import CompiledGlobals
from guppylang.definition.common import (
    CheckableDef,
    CheckedDef,
    DefId,
    Definition,
    ParsableDef,
    RawDef,
)
from guppylang.definition.declaration import RawFunctionDecl
from guppylang.definition.function import RawFunctionDef
from guppylang.definition.module import ModuleDef
from guppylang.definition.parameter import ParamDef
from guppylang.definition.struct import CheckedStructDef
from guppylang.definition.ty import TypeDef
from guppylang.error import GuppyError, pretty_errors
from guppylang.experimental import enable_experimental_features

PyClass = type
PyFunc = Callable[..., Any]
PyFuncDefOrDecl = tuple[bool, PyFunc]


class GuppyModule:
    """A Guppy module that may contain function and type definitions."""

    name: str

    # Whether the module has already been checked
    _checked: bool

    # Whether the module has already been compiled
    _compiled: bool

    # If the hugr has already been compiled, keeps a reference that can be returned
    # from `compile`.
    _compiled_hugr: Package | None

    # Map of raw definitions in this module
    _raw_defs: dict[DefId, RawDef]
    _raw_type_defs: dict[DefId, RawDef]

    # Map of checked definitions in this module. These are populated by calling `check`
    # on this module
    _checked_defs: dict[DefId, CheckedDef]

    # Globals from imported modules
    _imported_globals: Globals
    # Checked definitions from imported modules. Also includes transitively imported
    # definitions.
    _imported_checked_defs: dict[DefId, CheckedDef]

    # Globals for functions and types defined in this module. Only gets populated during
    # compilation
    _globals: Globals

    # When `_instance_buffer` is not `None`, then all registered functions will be
    # buffered in this list. They only get properly registered, once
    # `_register_buffered_instance_funcs` is called. This way, we can associate
    _instance_func_buffer: dict[str, RawDef] | None

    def __init__(self, name: str, import_builtins: bool = True):
        self.name = name
        self._globals = Globals({}, {}, {}, {})
        self._imported_globals = Globals.default()
        self._imported_checked_defs = {}
        self._checked = False
        self._compiled = False
        self._compiled_hugr = None
        self._instance_func_buffer = None
        self._raw_defs = {}
        self._raw_type_defs = {}
        self._checked_defs = {}

        # Import builtin module
        if import_builtins:
            import guppylang.prelude.builtins as builtins

            # Std lib is allowed to use experimental features
            with enable_experimental_features():
                self.load_all(builtins)

    def load(
        self,
        *args: "Definition | GuppyModule | ModuleType",
        **kwargs: "Definition | GuppyModule | ModuleType",
    ) -> None:
        """Imports another Guppy module or selected definitions from a module.

        Keyword args may be used to specify alias names for the imports.
        """
        modules: set[GuppyModule] = set()
        defs: dict[DefId, CheckedDef] = {}
        names: dict[str, DefId] = {}

        # Collect imports in reverse since we'll use it as a stack to push and pop from
        imports: list[tuple[str, Definition | GuppyModule | ModuleType]] = [
            *reversed(kwargs.items()),
            *(("", arg) for arg in reversed(args)),
        ]
        while imports:
            alias, imp = imports.pop()
            if isinstance(imp, Definition):
                module = imp.id.module
                assert module is not None
                module.check()
                names[alias or imp.name] = imp.id
                modules.add(module)
            elif isinstance(imp, GuppyModule):
                imp.check()
                def_id = DefId.fresh(imp)
                name = alias or imp.name
                defn = ModuleDef(def_id, name, None, imp._globals)
                defs[def_id] = defn
                names[name] = def_id
                modules.add(imp)
            elif isinstance(imp, ModuleType):
                mod = find_guppy_module_in_py_module(imp)
                imports.append((alias, mod))
            else:
                msg = f"Only Guppy definitions or modules can be imported. Got `{imp}`"
                raise GuppyError(msg)

        # Also include any impls that are defined by the imported modules
        impls: dict[DefId, dict[str, DefId]] = {}
        for module in modules:
            # We need to include everything defined in the module, including stuff that
            # is not directly imported, in order to lower everything into a single Hugr
            defs |= module._imported_checked_defs
            defs |= module._checked_defs
            # We also need to include any impls that are transitively imported
            all_globals = module._imported_globals | module._globals
            for def_id in all_globals.impls:
                impls.setdefault(def_id, {})
                impls[def_id] |= all_globals.impls[def_id]
        self._imported_globals |= Globals(dict(defs), names, impls, {})
        self._imported_checked_defs |= defs

        # We also need to include transitively imported checked definitions so we can
        # lower everything into one Hugr at the same time.
        for module in modules:
            self._imported_checked_defs |= module._imported_checked_defs

    def load_all(self, mod: "GuppyModule | ModuleType") -> None:
        """Imports all public members of a module."""
        if isinstance(mod, GuppyModule):
            mod.check()
            self.load(
                *(
                    defn
                    for defn in mod._globals.defs.values()
                    if not defn.name.startswith("_")
                )
            )
        elif isinstance(mod, ModuleType):
            self.load_all(find_guppy_module_in_py_module(mod))
        else:
            msg = f"Only Guppy definitions or modules can be imported. Got `{mod}`"
            raise GuppyError(msg)

    def register_def(self, defn: RawDef, instance: TypeDef | None = None) -> None:
        """Registers a definition with this module.

        If the name of the definition is already defined, the new definition
        replaces the old.

        Optionally, the definition can be marked as an instance method by passing the
        corresponding instance type definition.
        """
        self._checked = False
        self._compiled = False
        self._compiled_hugr = None
        if self._instance_func_buffer is not None and not isinstance(defn, TypeDef):
            self._instance_func_buffer[defn.name] = defn
        else:
            # If this overrides an already defined name, we need to purge the old
            # definition to avoid checking it later
            if self.contains(defn.name):
                self.unregister(self._globals[defn.name])
            if isinstance(defn, TypeDef | ParamDef):
                self._raw_type_defs[defn.id] = defn
            else:
                self._raw_defs[defn.id] = defn
            if instance is not None:
                self._globals.impls.setdefault(instance.id, {})
                self._globals.impls[instance.id][defn.name] = defn.id
            else:
                self._globals.names[defn.name] = defn.id
            self._globals.defs[defn.id] = defn

    def register_func_def(
        self, f: PyFunc, instance: TypeDef | None = None
    ) -> RawFunctionDef:
        """Registers a Python function definition as belonging to this Guppy module."""
        defn = RawFunctionDef(DefId.fresh(self), f.__name__, None, f, get_py_scope(f))
        self.register_def(defn, instance)
        return defn

    def register_func_decl(
        self, f: PyFunc, instance: TypeDef | None = None
    ) -> RawFunctionDecl:
        """Registers a Python function declaration as belonging to this Guppy module."""
        decl = RawFunctionDecl(DefId.fresh(self), f.__name__, None, f)
        self.register_def(decl, instance)
        return decl

    def _register_buffered_instance_funcs(self, instance: TypeDef) -> None:
        assert self._instance_func_buffer is not None
        buffer = self._instance_func_buffer
        self._instance_func_buffer = None
        for defn in buffer.values():
            self.register_def(defn, instance)

    def unregister(self, defn: Definition) -> None:
        """Removes a definition from this module.

        Also removes all methods when unregistering a type.
        """
        self._checked = False
        self._compiled = False
        self._compiled_hugr = None
        self._raw_defs.pop(defn.id, None)
        self._raw_type_defs.pop(defn.id, None)
        self._globals.defs.pop(defn.id, None)
        self._globals.names.pop(defn.name, None)
        if impls := self._globals.impls.pop(defn.id, None):
            for impl in impls.values():
                self.unregister(self._globals[impl])

    @property
    def checked(self) -> bool:
        return self._checked

    @property
    def compiled(self) -> bool:
        return self._compiled

    @staticmethod
    def _check_defs(
        raw_defs: Mapping[DefId, RawDef], globals: Globals
    ) -> dict[DefId, CheckedDef]:
        """Helper method to parse and check raw definitions."""
        raw_globals = globals | Globals(dict(raw_defs), {}, {}, {})
        parsed = {
            def_id: defn.parse(raw_globals) if isinstance(defn, ParsableDef) else defn
            for def_id, defn in raw_defs.items()
        }
        parsed_globals = globals | Globals(dict(parsed), {}, {}, {})
        return {
            def_id: (
                defn.check(parsed_globals) if isinstance(defn, CheckableDef) else defn
            )
            for def_id, defn in parsed.items()
        }

    def check(self) -> None:
        """Type-checks the module."""
        if self.checked:
            return

        # Type definitions need to be checked first so that we can use them when parsing
        # function signatures etc.
        type_defs = self._check_defs(
            self._raw_type_defs, self._imported_globals | self._globals
        )
        self._globals.defs.update(type_defs)

        # Collect auto-generated methods
        generated: dict[DefId, RawDef] = {}
        for defn in type_defs.values():
            if isinstance(defn, CheckedStructDef):
                self._globals.impls.setdefault(defn.id, {})
                for method_def in defn.generated_methods():
                    generated[method_def.id] = method_def
                    self._globals.impls[defn.id][method_def.name] = method_def.id
        self._globals.defs.update(generated)

        # Now, we can check all other definitions
        other_defs = self._check_defs(
            self._raw_defs | generated, self._imported_globals | self._globals
        )
        self._globals.defs.update(other_defs)
        self._checked_defs = type_defs | other_defs
        self._checked = True

    def compile_hugr(self) -> Hugr[ops.Module]:
        """Compiles the module and returns the final Hugr."""
        # This function does not use the `pretty_errors` decorator since it is
        # is wrapping around `compile_package` which does use it already.
        package = self.compile()
        hugr = package.modules[0]
        return hugr

    @pretty_errors
    def compile(self) -> Package:
        """Compiles the module and returns the final Hugr package.

        The package contains the single Hugr graph as well as the required
        extensions definitions.
        """
        if self.compiled:
            assert self._compiled_hugr is not None, "Module is compiled but has no Hugr"
            return self._compiled_hugr

        self.check()
        checked_defs = self._imported_checked_defs | self._checked_defs

        # Prepare Hugr for this module
        graph = Module()
        graph.metadata["name"] = self.name

        # Lower definitions to Hugr
        required = set(self._checked_defs.keys())
        ctx = CompiledGlobals(checked_defs, graph)
        _request_compilation = [ctx[def_id] for def_id in required]
        while ctx.worklist:
            next_id = ctx.worklist.pop()
            next_def = ctx[next_id]
            next_def.compile_inner(ctx)

        hugr = graph.hugr

        # TODO: Currently we just include a hardcoded list of extensions. We should
        # compute this dynamically from the imported dependencies instead.
        #
        # The hugr prelude extensions are implicit.
        from guppylang.prelude._internal.compiler.quantum import (
            HSERIES_EXTENSION,
            QUANTUM_EXTENSION,
            RESULT_EXTENSION,
        )

        extensions = [
            guppylang.compiler.hugr_extension.EXTENSION,
            QUANTUM_EXTENSION,
            HSERIES_EXTENSION,
            RESULT_EXTENSION,
        ]

        package = Package(modules=[hugr], extensions=extensions)
        self._compiled = True
        self._compiled_hugr = package

        return package

    def contains(self, name: str) -> bool:
        """Returns 'True' if the module contains an object with the given name."""
        return name in self._globals.names


def get_py_scope(f: PyFunc) -> PyScope:
    """Returns a mapping of all variables captured by a Python function.

    Note that this function only works in CPython. On other platforms, an empty
    dictionary is returned.

    Relies on inspecting the `__globals__` and `__closure__` attributes of the function.
    See https://docs.python.org/3/reference/datamodel.html#special-read-only-attributes
    """
    if sys.implementation.name != "cpython":
        return {}

    if inspect.ismethod(f):
        f = f.__func__
    code = f.__code__

    nonlocals: PyScope = {}
    if f.__closure__ is not None:
        for var, cell in zip(code.co_freevars, f.__closure__, strict=True):
            try:
                value = cell.cell_contents
            except ValueError:
                # The call to `cell_contents` will fail if `var` is a recursive
                # reference to the decorated function
                continue
            nonlocals[var] = value

    return nonlocals | f.__globals__.copy()


def find_guppy_module_in_py_module(module: ModuleType) -> GuppyModule:
    """Helper function to search the `__dict__` of a Python module for an instance of
     `GuppyModule`.

    Raises a user-error if no unique module can be found.
    """
    mods = [val for val in module.__dict__.values() if isinstance(val, GuppyModule)]
    # Also include implicit modules
    from guppylang.decorator import ModuleIdentifier, guppy

    if hasattr(module, "__file__") and module.__file__:
        module_id = ModuleIdentifier(Path(module.__file__), module.__name__, module)
        if module_id in guppy.registered_modules():
            mods.append(guppy.get_module(module_id))

    if not mods:
        msg = f"No Guppy modules found in `{module.__name__}`"
        raise GuppyError(msg)
    if len(mods) > 1:
        msg = (
            f"Python module `{module.__name__}` contains multiple Guppy modules. "
            "Cannot decide which one to import."
        )
        raise GuppyError(msg)
    return mods[0]
