import ast
import inspect
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any, ClassVar

from hugr import Wire, ops

from guppylang.ast_util import AstNode, annotate_location
from guppylang.checker.core import Globals, PyScope
from guppylang.checker.errors.generic import (
    ExpectedError,
    UnexpectedError,
    UnsupportedError,
)
from guppylang.definition.common import (
    CheckableDef,
    CompiledDef,
    DefId,
    ParsableDef,
    UnknownSourceError,
)
from guppylang.definition.custom import (
    CustomCallCompiler,
    CustomFunctionDef,
    DefaultCallChecker,
)
from guppylang.definition.parameter import ParamDef
from guppylang.definition.ty import TypeDef
from guppylang.diagnostic import Error, Help
from guppylang.error import GuppyError, InternalGuppyError
from guppylang.ipython_inspect import find_ipython_def, is_running_ipython
from guppylang.span import SourceMap
from guppylang.tracing.object import GuppyDefinition
from guppylang.tys.arg import Argument
from guppylang.tys.param import Parameter, check_all_args
from guppylang.tys.parsing import type_from_ast
from guppylang.tys.ty import FuncInput, FunctionType, InputFlags, StructType, Type


@dataclass(frozen=True)
class UncheckedStructField:
    """A single field on a struct whose type has not been checked yet."""

    name: str
    type_ast: ast.expr


@dataclass(frozen=True)
class StructField:
    """A single field on a struct."""

    name: str
    ty: Type


@dataclass(frozen=True)
class DuplicateFieldError(Error):
    title: ClassVar[str] = "Duplicate field"
    span_label: ClassVar[str] = (
        "Struct `{struct_name}` already contains a field named `{field_name}`"
    )
    struct_name: str
    field_name: str


@dataclass(frozen=True)
class NonGuppyMethodError(Error):
    title: ClassVar[str] = "Not a Guppy method"
    span_label: ClassVar[str] = (
        "Method `{method_name}` of struct `{struct_name}` is not a Guppy function"
    )
    struct_name: str
    method_name: str

    @dataclass(frozen=True)
    class Suggestion(Help):
        message: ClassVar[str] = (
            "Add a `@guppy` annotation to turn `{method_name}` into a Guppy method"
        )

    def __post_init__(self) -> None:
        self.add_sub_diagnostic(NonGuppyMethodError.Suggestion(None))


@dataclass(frozen=True)
class RawStructDef(TypeDef, ParsableDef):
    """A raw struct type definition that has not been parsed yet."""

    python_class: type
    python_scope: PyScope = field(repr=False)

    def __getitem__(self, item: Any) -> "RawStructDef":
        """Dummy implementation to enable subscripting in the Python runtime.

        For example, if users write `MyStruct[int]` in a function signature, the
        interpreter will try to execute the expression which would fail if this function
        weren't implemented.
        """
        return self

    def parse(self, globals: Globals, sources: SourceMap) -> "ParsedStructDef":
        """Parses the raw class object into an AST and checks that it is well-formed."""
        cls_def = parse_py_class(self.python_class, sources)
        if cls_def.keywords:
            raise GuppyError(UnexpectedError(cls_def.keywords[0], "keyword"))

        # The only base we allow is `Generic[...]` to specify generic parameters
        # TODO: This will become obsolete once we have Python 3.12 style generic classes
        params: list[Parameter]
        match cls_def.bases:
            case []:
                params = []
            case [base] if elems := try_parse_generic_base(base):
                params = params_from_ast(elems, globals)
            case bases:
                err: Error = UnsupportedError(
                    bases[0], "Struct inheritance", singular=True
                )
                raise GuppyError(err)

        fields: list[UncheckedStructField] = []
        used_field_names: set[str] = set()
        used_func_names: dict[str, ast.FunctionDef] = {}
        for i, node in enumerate(cls_def.body):
            match i, node:
                # We allow `pass` statements to define empty structs
                case _, ast.Pass():
                    pass
                # Docstrings are also fine if they occur at the start
                case 0, ast.Expr(value=ast.Constant(value=v)) if isinstance(v, str):
                    pass
                # Ensure that all function definitions are Guppy functions
                case _, ast.FunctionDef(name=name) as node:
                    v = getattr(self.python_class, name)
                    if not isinstance(v, GuppyDefinition):
                        raise GuppyError(NonGuppyMethodError(node, self.name, name))
                    used_func_names[name] = node
                    if name in used_field_names:
                        raise GuppyError(DuplicateFieldError(node, self.name, name))
                # Struct fields are declared via annotated assignments without value
                case _, ast.AnnAssign(target=ast.Name(id=field_name)) as node:
                    if node.value:
                        err = UnsupportedError(node.value, "Default struct values")
                        raise GuppyError(err)
                    if field_name in used_field_names:
                        err = DuplicateFieldError(node.target, self.name, field_name)
                        raise GuppyError(err)
                    fields.append(UncheckedStructField(field_name, node.annotation))
                    used_field_names.add(field_name)
                case _, node:
                    err = UnexpectedError(
                        node, "statement", unexpected_in="struct definition"
                    )
                    raise GuppyError(err)

        # Ensure that functions don't override struct fields
        if overridden := used_field_names.intersection(used_func_names.keys()):
            x = overridden.pop()
            raise GuppyError(DuplicateFieldError(used_func_names[x], self.name, x))

        return ParsedStructDef(
            self.id, self.name, cls_def, params, fields, self.python_scope
        )

    def check_instantiate(
        self, args: Sequence[Argument], globals: "Globals", loc: AstNode | None = None
    ) -> Type:
        raise InternalGuppyError("Tried to instantiate raw struct definition")


@dataclass(frozen=True)
class ParsedStructDef(TypeDef, CheckableDef):
    """A struct definition whose fields have not been checked yet."""

    defined_at: ast.ClassDef
    params: Sequence[Parameter]
    fields: Sequence[UncheckedStructField]
    python_scope: PyScope = field(repr=False)

    def check(self, globals: Globals) -> "CheckedStructDef":
        """Checks that all struct fields have valid types."""
        # Before checking the fields, make sure that this definition is not recursive,
        # otherwise the code below would not terminate.
        # TODO: This is not ideal (see todo in `check_instantiate`)
        globals = globals.with_python_scope(self.python_scope)
        param_var_mapping = {p.name: p for p in self.params}
        check_not_recursive(self, globals, param_var_mapping)

        fields = [
            StructField(f.name, type_from_ast(f.type_ast, globals, param_var_mapping))
            for f in self.fields
        ]
        return CheckedStructDef(
            self.id, self.name, self.defined_at, self.params, fields
        )

    def check_instantiate(
        self, args: Sequence[Argument], globals: "Globals", loc: AstNode | None = None
    ) -> Type:
        """Checks if the struct can be instantiated with the given arguments."""
        check_all_args(self.params, args, self.name, loc)
        # Obtain a checked version of this struct definition so we can construct a
        # `StructType` instance
        # TODO: This is quite bad: If we have a cyclic definition this will not
        #  terminate, so we have to check for cycles in every call to `check`. The
        #  proper way to deal with this is changing `StructType` such that it only
        #  takes a `DefId` instead of a `CheckedStructDef`. But this will be a bigger
        #  refactor...
        checked_def = self.check(globals)
        return StructType(args, checked_def)


@dataclass(frozen=True)
class CheckedStructDef(TypeDef, CompiledDef):
    """A struct definition that has been fully checked."""

    defined_at: ast.ClassDef
    params: Sequence[Parameter]
    fields: Sequence[StructField]

    def check_instantiate(
        self, args: Sequence[Argument], globals: "Globals", loc: AstNode | None = None
    ) -> Type:
        """Checks if the struct can be instantiated with the given arguments."""
        check_all_args(self.params, args, self.name, loc)
        return StructType(args, self)

    def generated_methods(self) -> list[CustomFunctionDef]:
        """Auto-generated methods for this struct."""

        class ConstructorCompiler(CustomCallCompiler):
            """Compiler for the `__new__` constructor method of a struct."""

            def compile(self, args: list[Wire]) -> list[Wire]:
                return list(self.builder.add(ops.MakeTuple()(*args)))

        constructor_sig = FunctionType(
            inputs=[
                FuncInput(f.ty, InputFlags.Owned if f.ty.linear else InputFlags.NoFlags)
                for f in self.fields
            ],
            output=StructType(
                defn=self, args=[p.to_bound(i) for i, p in enumerate(self.params)]
            ),
            input_names=[f.name for f in self.fields],
            params=self.params,
        )
        constructor_def = CustomFunctionDef(
            id=DefId.fresh(self.id.module),
            name="__new__",
            defined_at=self.defined_at,
            ty=constructor_sig,
            call_checker=DefaultCallChecker(),
            call_compiler=ConstructorCompiler(),
            higher_order_value=True,
            has_signature=True,
        )
        return [constructor_def]


def parse_py_class(cls: type, sources: SourceMap) -> ast.ClassDef:
    """Parses a Python class object into an AST."""
    # If we are running IPython, `inspect.getsourcelines` works only for builtins
    # (guppy stdlib), but not for most/user-defined classes - see:
    #  - https://bugs.python.org/issue33826
    #  - https://github.com/ipython/ipython/issues/11249
    #  - https://github.com/wandb/weave/pull/1864
    if is_running_ipython():
        defn = find_ipython_def(cls.__name__)
        if defn is not None:
            annotate_location(defn.node, defn.cell_source, f"<{defn.cell_name}>", 1)
            if not isinstance(defn.node, ast.ClassDef):
                raise GuppyError(ExpectedError(defn.node, "a class definition"))
            return defn.node
        # else, fall through to handle builtins.
    source_lines, line_offset = inspect.getsourcelines(cls)
    source = "".join(source_lines)  # Lines already have trailing \n's
    source = textwrap.dedent(source)
    cls_ast = ast.parse(source).body[0]
    file = inspect.getsourcefile(cls)
    if file is None:
        raise GuppyError(UnknownSourceError(None, cls))
    # Store the source file in our cache
    sources.add_file(file)
    annotate_location(cls_ast, source, file, line_offset)
    if not isinstance(cls_ast, ast.ClassDef):
        raise GuppyError(ExpectedError(cls_ast, "a class definition"))
    return cls_ast


def try_parse_generic_base(node: ast.expr) -> list[ast.expr] | None:
    """Checks if an AST node corresponds to a `Generic[T1, ..., Tn]` base class.

    Returns the generic parameters or `None` if the AST has a different shape
    """
    match node:
        case ast.Subscript(value=ast.Name(id="Generic"), slice=elem):
            return elem.elts if isinstance(elem, ast.Tuple) else [elem]
        case _:
            return None


@dataclass(frozen=True)
class RepeatedTypeParamError(Error):
    title: ClassVar[str] = "Duplicate type parameter"
    span_label: ClassVar[str] = "Type parameter `{name}` cannot be used multiple times"
    name: str


def params_from_ast(nodes: Sequence[ast.expr], globals: Globals) -> list[Parameter]:
    """Parses a list of AST nodes into unique type parameters.

    Raises user errors if the AST nodes don't correspond to parameters or parameters
    occur multiple times.
    """
    params: list[Parameter] = []
    params_set: set[DefId] = set()
    for node in nodes:
        if isinstance(node, ast.Name) and node.id in globals:
            defn = globals[node.id]
            if isinstance(defn, ParamDef):
                if defn.id in params_set:
                    raise GuppyError(RepeatedTypeParamError(node, node.id))
                params.append(defn.to_param(len(params)))
                params_set.add(defn.id)
                continue
        raise GuppyError(ExpectedError(node, "a type parameter"))
    return params


def check_not_recursive(
    defn: ParsedStructDef, globals: Globals, param_var_mapping: dict[str, Parameter]
) -> None:
    """Throws a user error if the given struct definition is recursive."""

    # TODO: The implementation below hijacks the type parsing logic to detect recursive
    #  structs. This is not great since it repeats the work done during checking. We can
    #  get rid of this after resolving the todo in `ParsedStructDef.check_instantiate()`

    @dataclass(frozen=True)
    class DummyStructDef(TypeDef):
        """Dummy definition that throws an error when trying to instantiate it.

        By replacing the defn with this, we can detect recursive occurrences during
        type parsing.
        """

        def check_instantiate(
            self,
            args: Sequence[Argument],
            globals: "Globals",
            loc: AstNode | None = None,
        ) -> Type:
            raise GuppyError(UnsupportedError(loc, "Recursive structs"))

    dummy_defs = {
        **globals.defs,
        defn.id: DummyStructDef(defn.id, defn.name, defn.defined_at),
    }
    dummy_globals = replace(globals, defs=globals.defs | dummy_defs)
    for fld in defn.fields:
        type_from_ast(fld.type_ast, dummy_globals, param_var_mapping)
