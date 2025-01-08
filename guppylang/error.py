import functools
import os
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING, Any, TypeVar, cast

from guppylang.ipython_inspect import is_running_ipython

if TYPE_CHECKING:
    from guppylang.diagnostic import Error, Fatal


@dataclass
class GuppyError(Exception):
    """An error that occurs during compilation."""

    error: "Error | Fatal"


class GuppyTypeError(GuppyError):
    """Special Guppy exception for type errors."""


class GuppyTypeInferenceError(GuppyError):
    """Special Guppy exception for type inference errors."""


class MissingModuleError(Exception):
    """Special Guppy exception for operations that require a guppy module."""


class InternalGuppyError(Exception):
    """Exception for internal problems during compilation."""


ExceptHook = Callable[[type[BaseException], BaseException, TracebackType | None], Any]


@contextmanager
def exception_hook(hook: ExceptHook) -> Iterator[None]:
    """Sets a custom `excepthook` for the scope of a 'with' block."""
    try:
        # Check if we're inside a jupyter notebook since it uses its own exception
        # hook. If we're in a regular interpreter, this line will raise a `NameError`
        ipython_shell = get_ipython()  # type: ignore[name-defined]

        def ipython_excepthook(
            shell: Any,
            etype: type[BaseException],
            value: BaseException,
            tb: TracebackType | None,
            tb_offset: Any = None,
        ) -> Any:
            return hook(etype, value, tb)

        old_hook = ipython_shell.CustomTB
        old_exc_tuple = ipython_shell.custom_exceptions
        ipython_shell.set_custom_exc((Exception,), ipython_excepthook)
        yield
        ipython_shell.set_custom_exc(
            old_exc_tuple, lambda shell, *args, **kwargs: old_hook(*args, **kwargs)
        )
    except NameError:
        pass
    else:
        return

    # Otherwise, override the regular sys.excepthook
    old_hook = sys.excepthook
    sys.excepthook = hook
    yield
    sys.excepthook = old_hook


FuncT = TypeVar("FuncT", bound=Callable[..., Any])


def pretty_errors(f: FuncT) -> FuncT:
    """Decorator to print custom error banners when a `GuppyError` occurs."""

    def hook(
        excty: type[BaseException], err: BaseException, traceback: TracebackType | None
    ) -> None:
        """Custom `excepthook` that intercepts `GuppyExceptions` for pretty printing."""
        if isinstance(err, GuppyError):
            from guppylang.decorator import guppy
            from guppylang.diagnostic import DiagnosticsRenderer

            renderer = DiagnosticsRenderer(guppy._sources)
            renderer.render_diagnostic(err.error)
            sys.stderr.write("\n".join(renderer.buffer))
            sys.stderr.write("\n\nGuppy compilation failed due to 1 previous error\n")
            return

        # If it's not a GuppyError, fall back to default hook
        sys.__excepthook__(excty, err, traceback)

    @functools.wraps(f)
    def pretty_errors_wrapped(*args: Any, **kwargs: Any) -> Any:
        with exception_hook(hook):
            try:
                return f(*args, **kwargs)
            except GuppyError as err:
                # For normal usage, this `try` block is not necessary since the
                # excepthook is automatically invoked when the exception (which is being
                # reraised below) is not handled. However, when running tests, we have
                # to manually invoke the hook to print the error message, since the
                # tests always have to capture exceptions. The only exception are
                # notebook tests which don't rely on the capsys fixture.
                if _pytest_running() and not is_running_ipython():
                    hook(type(err), err, err.__traceback__)
                raise

    return cast(FuncT, pretty_errors_wrapped)


def _pytest_running() -> bool:
    """Checks if we are currently running pytest.

    See https://docs.pytest.org/en/latest/example/simple.html#pytest-current-test-environment-variable
    """
    return "PYTEST_CURRENT_TEST" in os.environ
