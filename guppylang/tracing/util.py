import functools
import inspect
import sys
from collections.abc import Callable
from types import FrameType, TracebackType
from typing import ParamSpec, TypeVar

from guppylang.error import GuppyError, exception_hook

P = ParamSpec("P")
T = TypeVar("T")


def hide_trace(f: Callable[P, T]) -> Callable[P, T]:
    """Function decorator that hides compiler-internal frames from the traceback of any
    exception thrown by the decorated function."""

    @functools.wraps(f)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        with exception_hook(tracing_except_hook):
            return f(*args, **kwargs)

    return wrapped


def tracing_except_hook(
    excty: type[BaseException], err: BaseException, traceback: TracebackType | None
) -> None:
    """Except hook that removes all compiler-internal frames from the traceback."""
    if isinstance(err, GuppyError):
        diagnostic = err.error
        msg = diagnostic.rendered_title
        if diagnostic.span_label:
            msg += f": {diagnostic.rendered_span_label}"
        if diagnostic.message:
            msg += f"\n{diagnostic.rendered_message}"
        err = RuntimeError(msg)
        excty = RuntimeError

    traceback = remove_internal_frames(traceback)
    try:
        # Check if we're inside a jupyter notebook since it uses its own exception
        # hook. If we're in a regular interpreter, this line will raise a `NameError`
        ipython_shell = get_ipython()  # type: ignore[name-defined]
        ipython_shell.excepthook(excty, err, traceback)
    except NameError:
        sys.__excepthook__(excty, err, traceback)


def get_calling_frame() -> FrameType | None:
    """Finds the first frame that called this function outside the compiler."""
    frame = inspect.currentframe()
    while frame:
        module = inspect.getmodule(frame)
        if module is None or not module.__name__.startswith("guppylang."):
            return frame
        frame = frame.f_back
    return None


def remove_internal_frames(tb: TracebackType | None) -> TracebackType | None:
    if tb:
        module = inspect.getmodule(tb.tb_frame)
        if module is not None and module.__name__.startswith("guppylang."):
            return remove_internal_frames(tb.tb_next)
        if tb.tb_next:
            tb.tb_next = remove_internal_frames(tb.tb_next)
    return tb
