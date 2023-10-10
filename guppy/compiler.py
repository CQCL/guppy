import ast
import functools
import inspect
import sys
import textwrap
from dataclasses import dataclass
from types import ModuleType
from typing import Optional, Any, Callable, Union

from guppy.ast_util import is_empty_body
from guppy.compiler_base import Globals
from guppy.extension import GuppyExtension
from guppy.function import FunctionDefCompiler, DefinedFunction
from guppy.hugr.hugr import Hugr
from guppy.error import GuppyError, SourceLoc


def format_source_location(
    source_lines: list[str],
    loc: Union[ast.AST, ast.operator, ast.expr, ast.arg, ast.Name],
    line_offset: int,
    num_lines: int = 3,
    indent: int = 4,
) -> str:
    """Creates a pretty banner to show source locations for errors."""
    assert loc.end_col_offset is not None  # TODO
    s = "".join(source_lines[max(loc.lineno - num_lines, 0) : loc.lineno]).rstrip()
    s += "\n" + loc.col_offset * " " + (loc.end_col_offset - loc.col_offset) * "^"
    s = textwrap.dedent(s).splitlines()
    # Add line numbers
    line_numbers = [
        str(line_offset + loc.lineno - i) + ":" for i in range(num_lines, 0, -1)
    ]
    longest = max(len(ln) for ln in line_numbers)
    prefixes = [ln + " " * (longest - len(ln) + indent) for ln in line_numbers]
    res = "".join(prefix + line + "\n" for prefix, line in zip(prefixes, s[:-1]))
    res += (longest + indent) * " " + s[-1]
    return res


def get_python_vars() -> dict[str, Any]:
    """Looks up all active variables from the call-site.

    Walks up the call stack until we have left the compiler module.
    """
    # Note that this approach will yield unintended results if the user doesn't invoke
    # the decorator directly. For example:
    #
    #       def my_dec(f):
    #           some_local = ...
    #           return guppy(f)
    #
    #       @my_dec
    #       def guppy_func(x: int) -> int:
    #           ....
    #
    # Here, we would reach the scope of `my_dec` and `some_local` would be available
    # in the Guppy code.
    # TODO: Is there a better way to obtain the variables in scope? Note that we
    #  could do `inspect.getclosurevars(f)` but it will fail if `f` has recursive
    #  calls. A custom solution based on `f.__code__.co_freevars` and
    #  `f.__closure__` would only work for CPython.
    frame = inspect.currentframe()
    if frame is None:
        return {}
    while frame.f_back is not None and frame.f_globals["__name__"] == __name__:
        frame = frame.f_back
    py_scope = frame.f_globals | frame.f_locals
    # Explicitly delete frame to avoid reference cycle.
    # See https://docs.python.org/3/library/inspect.html#the-interpreter-stack
    del frame
    return py_scope


@dataclass
class RawFunction:
    pyfun: Callable[..., Any]
    ast: ast.FunctionDef
    source_lines: list[str]
    line_offset: int
    python_vals: dict[str, Any]


class GuppyModule(object):
    """A Guppy module backed by a Hugr graph.

    Instances of this class can be used as a decorator to add functions to the module.
    After all functions are added, `compile()` must be called to obtain the Hugr.
    """

    name: str
    globals: Globals

    _func_defs: dict[str, RawFunction]
    _func_decls: dict[str, RawFunction]

    def __init__(self, name: str):
        self.name = name
        self.globals = Globals.default()
        self._func_defs = {}
        self._func_decls = {}

        # Load all prelude extensions
        import guppy.prelude.builtin
        import guppy.prelude.boolean
        import guppy.prelude.float
        import guppy.prelude.integer

        self.load(guppy.prelude.builtin)
        self.load(guppy.prelude.boolean)
        self.load(guppy.prelude.float)
        self.load(guppy.prelude.integer)

    def register_func(self, f: Callable[..., Any]) -> None:
        """Registers a Python function as belonging to this Guppy module.

        This can be used for both function definitions and declarations. To mark a
        declaration, the body of the function may only contain an ellipsis expression.
        """
        func = self._parse(f)
        if is_empty_body(func.ast):
            self._func_decls[func.ast.name] = func
        else:
            self._func_defs[func.ast.name] = func

    def load(self, m: Union[ModuleType, GuppyExtension]) -> None:
        """Loads a Guppy extension from a python module.

        This function must be called for names from the extension to become available in
        the Guppy.
        """
        if isinstance(m, GuppyExtension):
            self.globals |= m.globals
        else:
            for ext in m.__dict__.values():
                if isinstance(ext, GuppyExtension):
                    self.globals |= ext.globals

    def _parse(self, f: Callable[..., Any]) -> RawFunction:
        source_lines, line_offset = inspect.getsourcelines(f)
        line_offset -= 1
        source = "".join(source_lines)  # Lines already have trailing \n's
        source = textwrap.dedent(source)
        func_ast = ast.parse(source).body[0]
        if not isinstance(func_ast, ast.FunctionDef):
            raise GuppyError("Only functions can be placed in modules", func_ast)
        if func_ast.name in self._func_defs:
            raise GuppyError(
                f"Module `{self.name}` already contains a function named `{func_ast.name}` "
                f"(declared at {SourceLoc.from_ast(self._func_defs[func_ast.name].ast, line_offset)})",
                func_ast,
            )
        return RawFunction(f, func_ast, source_lines, line_offset, get_python_vars())

    def compile(self, exit_on_error: bool = False) -> Optional[Hugr]:
        """Compiles the module and returns the final Hugr."""
        graph = Hugr(self.name)
        module_node = graph.set_root_name(self.name)
        try:
            # Generate nodes for all function definition and declarations and add them
            # to the globals
            defs = {}
            for name, f in self._func_defs.items():
                func_ty = FunctionDefCompiler.validate_signature(f.ast, self.globals)
                def_node = graph.add_def(func_ty, module_node, f.ast.name)
                defs[name] = def_node
                self.globals.values[name] = DefinedFunction(
                    name, def_node.out_port(0), f.ast
                )
            for name, f in self._func_decls.items():
                func_ty = FunctionDefCompiler.validate_signature(f.ast, self.globals)
                if not is_empty_body(f.ast):
                    raise GuppyError(
                        "Function declarations may not have a body.", f.ast.body[0]
                    )
                decl_node = graph.add_declare(func_ty, module_node, f.ast.name)
                self.globals.values[name] = DefinedFunction(
                    name, decl_node.out_port(0), f.ast
                )

            # Now compile functions definitions
            for name, f in self._func_defs.items():
                globs = self.globals | Globals({}, {}, {}, f.python_vals)
                FunctionDefCompiler(graph, globs).compile_global(f.ast, defs[name])
            return graph

        except GuppyError as err:
            if err.location:
                loc = err.location
                line = f.line_offset + loc.lineno
                print(
                    "Guppy compilation failed. "
                    f"Error in file {inspect.getsourcefile(f.pyfun)}:{line}\n",
                    file=sys.stderr,
                )
                print(
                    format_source_location(f.source_lines, loc, f.line_offset + 1),
                    file=sys.stderr,
                )
            else:
                print(
                    "Guppy compilation failed. "
                    f"Error in file {inspect.getsourcefile(f.pyfun)}\n",
                    file=sys.stderr,
                )
            print(
                f"{err.__class__.__name__}: {err.get_msg(f.line_offset)}",
                file=sys.stderr,
            )
            if exit_on_error:
                sys.exit(1)
            return None


def guppy(
    arg: Union[Callable[..., Any], GuppyModule]
) -> Union[Optional[Hugr], Callable[[Callable[..., Any]], Callable[..., Any]]]:
    """Decorator to annotate Python functions as Guppy code.

    Optionally, the `GuppyModule` in which the function should be placed can be passed
    to the decorator.
    """
    if isinstance(arg, GuppyModule):

        def dec(f: Callable[..., Any]) -> Callable[..., Any]:
            assert isinstance(arg, GuppyModule)
            arg.register_func(f)

            @functools.wraps(f)
            def dummy(*args: Any, **kwargs: Any) -> Any:
                raise GuppyError(
                    "Guppy functions can only be called in a Guppy context"
                )

            return dummy

        return dec
    else:
        module = GuppyModule("module")
        module.register_func(arg)
        return module.compile(exit_on_error=False)
