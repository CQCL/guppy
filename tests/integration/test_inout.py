import pytest


from guppylang.decorator import guppy
from guppylang.module import GuppyModule
from guppylang.std.builtins import owned
from guppylang.std.quantum import qubit

import guppylang.std.quantum as quantum


def test_basic(validate):
    module = GuppyModule("test")
    module.load_all(quantum)

    @guppy.declare(module)
    def foo(q: qubit) -> None: ...

    @guppy(module)
    def test(q: qubit @ owned) -> qubit:
        foo(q)
        return q

    validate(module.compile())


def test_mixed(validate):
    module = GuppyModule("test")
    module.load_all(quantum)

    @guppy.declare(module)
    def foo(q1: qubit, q2: qubit @ owned) -> qubit: ...

    @guppy(module)
    def test(q1: qubit @ owned, q2: qubit @ owned) -> tuple[qubit, qubit]:
        q2 = foo(q1, q2)
        return q1, q2

    validate(module.compile())


def test_local(validate):
    module = GuppyModule("test")
    module.load_all(quantum)

    @guppy.declare(module)
    def foo(q: qubit) -> None: ...

    @guppy(module)
    def test(q: qubit @ owned) -> qubit:
        f = foo
        f(q)
        return q

    validate(module.compile())


def test_nested_calls(validate):
    module = GuppyModule("test")
    module.load_all(quantum)

    @guppy.declare(module)
    def foo(x: int, q: qubit) -> int: ...

    @guppy(module)
    def test(q: qubit @ owned) -> tuple[int, qubit]:
        # This is legal since function arguments and tuples are evaluated left to right
        return foo(foo(foo(0, q), q), q), q

    validate(module.compile())


def test_struct(validate):
    module = GuppyModule("test")
    module.load_all(quantum)

    @guppy.struct(module)
    class MyStruct:
        q1: qubit
        q2: qubit

    @guppy.declare(module)
    def foo(q1: qubit, q2: qubit) -> None: ...

    @guppy.declare(module)
    def bar(a: MyStruct) -> None: ...

    @guppy(module)
    def test1(a: MyStruct @ owned) -> MyStruct:
        foo(a.q1, a.q2)
        bar(a)
        return a

    @guppy(module)
    def test2(a: MyStruct @ owned) -> MyStruct:
        bar(a)
        foo(a.q1, a.q2)
        bar(a)
        return a

    validate(module.compile())


def test_control_flow(validate):
    module = GuppyModule("test")
    module.load_all(quantum)

    @guppy.declare(module)
    def foo(q: qubit) -> None: ...

    @guppy.declare(module)
    def bar(q: qubit) -> bool: ...

    @guppy(module)
    def test(q1: qubit @ owned, q2: qubit @ owned, n: int) -> tuple[qubit, qubit]:
        i = 0
        while i < n:
            foo(q1)
            if bar(q1) or bar(q2):
                foo(q2)
                continue
            elif not bar(q2):
                return q1, q2
            foo(q1)
            if bar(q2):
                foo(q1)
                break
            else:
                foo(q2)
            foo(q2)
            foo(q1)
            if bar(q2) and bar(q1):
                if i > 5:
                    foo(q2)
                return q1, q2
            foo(q1)
            i += 1
        return q1, q2

    validate(module.compile())


def test_tensor(validate):
    module = GuppyModule("test")
    module.load_all(quantum)

    @guppy.struct(module)
    class A:
        q: qubit

    @guppy.struct(module)
    class B:
        q: qubit
        x: int

    @guppy.struct(module)
    class C:
        q: qubit
        x: float

    @guppy.declare(module)
    def foo(a: A, x: int) -> None: ...

    @guppy.declare(module)
    def bar(y: float, b: B, c: C @ owned) -> C: ...

    @guppy.declare(module)
    def baz(c: C) -> None: ...

    @guppy(module)
    def test(
        a: A @ owned, b: B @ owned, c1: C @ owned, c2: C @ owned, x: bool
    ) -> tuple[A, B, C, C]:
        c1 = (foo, bar, baz)(a, b.x, c1.x, b, c1, c2)
        if x:
            c1 = ((foo, bar), baz)(a, b.x, c1.x, b, c1, c2)
        c1 = (foo, (bar, baz))(a, b.x, c1.x, b, c1, c2)
        return a, b, c1, c2

    validate(module.compile())


def test_basic_def(validate):
    module = GuppyModule("test")
    module.load_all(quantum)

    @guppy.declare(module)
    def h(q: qubit) -> None: ...

    @guppy(module)
    def foo(q: qubit) -> None:
        h(q)
        h(q)

    @guppy(module)
    def test(q: qubit @ owned) -> qubit:
        foo(q)
        foo(q)
        return q

    validate(module.compile())


def test_empty_def(validate):
    module = GuppyModule("test")
    module.load_all(quantum)

    @guppy(module)
    def test(q: qubit) -> None:
        pass

    @guppy(module)
    def main(q: qubit @ owned) -> qubit:
        test(q)
        return q

    validate(module.compile())


def test_mixed_def(validate):
    module = GuppyModule("test")
    module.load_all(quantum)

    @guppy.declare(module)
    def foo(q: qubit) -> None: ...

    @guppy(module)
    def test(
        b: int, c: qubit, d: float, a: tuple[qubit, qubit], e: qubit @ owned
    ) -> tuple[qubit, float]:
        foo(c)
        return e, b + d

    validate(module.compile())


def test_move_back(validate):
    module = GuppyModule("test")
    module.load_all(quantum)

    @guppy.struct(module)
    class MyStruct:
        q: qubit

    @guppy.declare(module)
    def use(q: qubit @ owned) -> None: ...

    @guppy(module)
    def foo(s: MyStruct) -> None:
        use(s.q)
        s.q = qubit()

    @guppy(module)
    def bar(s: MyStruct) -> None:
        s.q = s.q

    @guppy(module)
    def swap(s: MyStruct, t: MyStruct) -> None:
        s.q, t.q = t.q, s.q

    @guppy(module)
    def main(s: MyStruct @ owned, t: MyStruct @ owned) -> MyStruct:
        foo(s)
        swap(s, t)
        bar(t)
        use(t.q)
        return s

    validate(module.compile())


def test_move_back_branch(validate):
    module = GuppyModule("test")
    module.load_all(quantum)

    @guppy.struct(module)
    class MyStruct:
        q: qubit

    @guppy.declare(module)
    def use(q: qubit @ owned) -> None: ...

    @guppy(module)
    def test(
        s: MyStruct, b: bool, n: int, q1: qubit @ owned, q2: qubit @ owned
    ) -> None:
        use(s.q)
        if b:
            s.q = q1
            use(q2)
        else:
            s.q = q2
            use(q1)
        use(s.q)
        i = 0
        while True:
            if i == n:
                s.q = qubit()
                return
            i += 1

    @guppy(module)
    def main(s: MyStruct @ owned) -> MyStruct:
        test(s, False, 5, qubit(), qubit())
        return s

    validate(module.compile())


def test_self(validate):
    module = GuppyModule("test")
    module.load_all(quantum)

    @guppy.declare(module)
    def foo(q: qubit) -> None: ...

    @guppy.struct(module)
    class MyStruct:
        q: qubit

        @guppy(module)
        def bar(self: "MyStruct", b: bool) -> None:
            foo(self.q)
            if b:
                foo(self.q)

    validate(module.compile())


def test_subtype(validate):
    module = GuppyModule("test")
    module.load_all(quantum)

    @guppy.declare(module)
    def foo(q: qubit) -> None: ...

    @guppy(module)
    def main() -> qubit:
        q = qubit()
        foo(q)
        return q

    validate(module.compile())


def test_shadow_check(validate):
    module = GuppyModule("test")

    module.load(quantum, qubit)

    @guppy.declare(module)
    def foo(i: qubit) -> None: ...

    @guppy(module)
    def main(i: qubit) -> None:
        if True:
            foo(i)

    validate(module.compile())


def test_self_qubit(validate):
    module = GuppyModule("test")
    module.load(qubit)

    @guppy(module)
    def test() -> bool:
        q0 = qubit()

        result = q0.project_z()
        q0.measure()
        qubit().discard()
        return result

    validate(module.compile())


def test_non_terminating(validate):
    module = GuppyModule("test")
    module.load_all(quantum)

    @guppy.struct(module)
    class MyStruct:
        q1: qubit
        q2: qubit
        x: int

    @guppy.declare(module)
    def foo(q: qubit) -> None: ...

    @guppy.declare(module)
    def bar(s: MyStruct) -> None: ...

    @guppy(module)
    def test1(b: bool) -> None:
        q = qubit()
        s = MyStruct(qubit(), qubit(), 0)
        while True:
            foo(q)
            bar(s)

    @guppy(module)
    def test2(q: qubit, s: MyStruct, b: bool) -> None:
        while True:
            foo(q)
            if b:
                bar(s)

    @guppy(module)
    def test3(q: qubit, s: MyStruct) -> None:
        while True:
            pass

    validate(module.compile())
