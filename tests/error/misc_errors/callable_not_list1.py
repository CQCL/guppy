from typing import Callable

from guppylang.decorator import guppy
from guppylang.module import GuppyModule


module = GuppyModule("test")

@guppy.declare(module)
def foo(f: "Callable[int, float, bool]") -> None: ...


module.compile()
