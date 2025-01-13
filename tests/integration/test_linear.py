from guppylang.decorator import guppy
from guppylang.module import GuppyModule
from guppylang.std.builtins import owned
from guppylang.std.quantum import qubit, measure

import guppylang.std.quantum_functional as quantum_functional
from guppylang.std.quantum_functional import cx, t, h, project_z
from guppylang.tys.ty import NoneType

import pytest


def test_id(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy(module)
    def test(q: qubit @owned) -> qubit:
        return q

    validate(module.compile())


def test_assign(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy(module)
    def test(q: qubit @owned) -> qubit:
        r = q
        s = r
        return s

    validate(module.compile())


def test_linear_return_order(validate):
    # See https://github.com/CQCL-DEV/guppy/issues/35
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy(module)
    def test(q: qubit @owned) -> tuple[qubit, bool]:
        return project_z(q)

    validate(module.compile())


def test_interleave(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy.declare(module)
    def f(q1: qubit @owned, q2: qubit @owned) -> tuple[qubit, qubit]: ...

    @guppy.declare(module)
    def g(q1: qubit @owned, q2: qubit @owned) -> tuple[qubit, qubit]: ...

    @guppy(module)
    def test(
        a: qubit @owned, b: qubit @owned, c: qubit @owned, d: qubit @owned
    ) -> tuple[qubit, qubit, qubit, qubit]:
        a, b = f(a, b)
        c, d = f(c, d)
        b, c = g(b, c)
        return a, b, c, d

    validate(module.compile())


def test_linear_struct(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy.struct(module)
    class MyStruct:
        q1: qubit
        q2: qubit

    @guppy.declare(module)
    def f(q1: qubit @owned, q2: qubit @owned) -> tuple[qubit, qubit]: ...

    @guppy.declare(module)
    def g(q1: qubit @owned, q2: qubit @owned) -> tuple[qubit, qubit]: ...

    @guppy(module)
    def construct(q1: qubit @owned, q2: qubit @owned) -> MyStruct:
        return MyStruct(q1, q2)

    @guppy(module)
    def test(s: MyStruct @owned, t: MyStruct @owned) -> tuple[qubit, qubit, qubit, qubit]:
        s.q1, s.q2 = f(s.q2, s.q1)
        t.q1, t.q2 = f(t.q1, t.q2)
        s.q2, t.q1 = g(t.q1, s.q2)
        return s.q1, s.q2, t.q1, t.q2

    validate(module.compile())


def test_mixed_classical_linear_struct(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy.struct(module)
    class MyStruct:
        q: qubit
        x: int
        y: float

    @guppy.declare(module)
    def f(q: qubit @owned) -> qubit: ...

    @guppy(module)
    def test1(s: MyStruct @owned) -> tuple[MyStruct, float]:
        a = s.x + s.y
        s.q = f(s.q)
        return s, a * s.x

    @guppy(module)
    def test2(s: MyStruct @owned) -> tuple[MyStruct, int, int, int]:
        t = s
        u = t
        u.q = f(u.q)
        return u, s.x, t.x, u.x

    validate(module.compile())


def test_drop_classical_field(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy.struct(module)
    class MyStruct:
        q: qubit
        x: int

    @guppy.declare(module)
    def f() -> MyStruct: ...

    @guppy(module)
    def test() -> qubit:
        return f().q


def test_if(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy(module)
    def test(b: bool) -> qubit:
        if b:
            a = qubit()
            q = h(a)
        else:
            q = qubit()
        return q

    validate(module.compile())


def test_if_return(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy(module)
    def test(b: bool) -> qubit:
        if b:
            q = qubit()
            return h(q)
        else:
            q = qubit()
        return q

    validate(module.compile())


def test_if_struct_rebuild(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy.struct(module)
    class MyStruct:
        q: qubit

    @guppy(module)
    def test1(s: MyStruct @owned, b: bool) -> MyStruct:
        if b:
            s = MyStruct(s.q)
        return s

    @guppy(module)
    def test2(s: MyStruct @owned, b: bool) -> MyStruct:
        if b:
            s.q = s.q
        return s

    validate(module.compile())


def test_struct_reassign(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy.struct(module)
    class MyStruct1:
        x: "MyStruct2"

    @guppy.struct(module)
    class MyStruct2:
        q: qubit

    @guppy.declare(module)
    def consume(s: MyStruct2 @owned) -> None: ...

    @guppy(module)
    def test(s: MyStruct2 @owned, b: bool) -> MyStruct2:
        consume(s)
        if b:
            s = MyStruct2(qubit())
            return s
        else:
            s = MyStruct1(MyStruct2(qubit()))
        return s.x


def test_struct_reassign2(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy.struct(module)
    class MyStruct:
        q1: qubit
        q2: qubit

    @guppy.declare(module)
    def use(q: qubit @owned) -> None: ...

    @guppy(module)
    def test(s: MyStruct @owned, b: bool) -> MyStruct:
        use(s.q1)
        if b:
            s.q1 = qubit()
        else:
            s.q1 = qubit()
        s.q2 = qubit()
        return s


def test_measure(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit, measure)

    @guppy(module)
    def test(q: qubit @owned, x: int) -> int:
        b = measure(q)
        return x

    validate(module.compile())


def test_return_call(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy.declare(module)
    def op(q: qubit @owned) -> qubit: ...

    @guppy(module)
    def test(q: qubit @owned) -> qubit:
        return op(q)

    validate(module.compile())


def test_while(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy(module)
    def test(q: qubit @owned, i: int) -> qubit:
        while i > 0:
            i -= 1
            q = h(q)
        return q

    validate(module.compile())


def test_while_break(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy(module)
    def test(q: qubit @owned, i: int) -> qubit:
        while i > 0:
            i -= 1
            q = h(q)
            if i < 5:
                break
        return q

    validate(module.compile())


def test_while_continue(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy(module)
    def test(q: qubit @owned, i: int) -> qubit:
        while i > 0:
            i -= 1
            if i % 3 == 0:
                continue
            q = h(q)
        return q

    validate(module.compile())


def test_while_reset(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy(module)
    def foo(i: bool) -> bool:
        b = False
        while True:
            q = qubit()
            b ^= measure(q)
            if i == 0:
                break
            i -= 1
        return b


def test_while_move_back(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy.struct(module)
    class MyStruct:
        q: qubit

    @guppy.declare(module)
    def use(q: qubit @owned) -> None: ...

    @guppy(module)
    def test(s: MyStruct @owned) -> MyStruct:
        use(s.q)
        while True:
            s.q = qubit()
            return s

    validate(module.compile())


def test_for(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy(module)
    def test(qs: list[tuple[qubit, qubit]] @owned) -> list[qubit]:
        rs: list[qubit] = []
        for q1, q2 in qs:
            q1, q2 = cx(q1, q2)
            rs.append(q1)
            rs.append(q2)
        return rs

    validate(module.compile())


def test_for_measure(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit, measure)

    @guppy(module)
    def test(qs: list[qubit] @owned) -> bool:
        parity = False
        for q in qs:
            parity |= measure(q)
        return parity

    validate(module.compile())


def test_for_continue(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit, measure)

    @guppy(module)
    def test(qs: list[qubit] @owned) -> int:
        x = 0
        for q in qs:
            if measure(q):
                continue
            x += 1
        return x

    validate(module.compile())


def test_for_nonlinear_break(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy.type(NoneType().to_hugr(), module=module)
    class MyIter:
        """An iterator that yields linear values but is not linear itself."""

        @guppy.declare(module)
        def __hasnext__(self: "MyIter") -> tuple[bool, "MyIter"]: ...

        @guppy.declare(module)
        def __next__(self: "MyIter") -> tuple[qubit, "MyIter"]: ...

        @guppy.declare(module)
        def __end__(self: "MyIter") -> None: ...

    @guppy.type(NoneType().to_hugr(), module=module)
    class MyType:
        """Type that produces the iterator above."""

        @guppy.declare(module)
        def __iter__(self: "MyType") -> MyIter: ...

    @guppy.declare(module)
    def measure(q: qubit @owned) -> bool: ...

    @guppy(module)
    def test(mt: MyType, xs: list[int]) -> None:
        # We can break, since `mt` itself is not linear
        for q in mt:
            if measure(q):
                break

    validate(module.compile())


def test_rus(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit, measure)

    @guppy(module)
    def repeat_until_success(q: qubit @owned) -> qubit:
        while True:
            aux, q = cx(t(h(qubit())), q)
            aux, q = cx(h(aux), q)
            if measure(h(t(aux))):
                break
        return q

    validate(module.compile())

def test_list_iter_arg(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy(module)
    def owned_arg(qs: list[qubit] @owned) -> list[qubit]:
        qs = [h(q) for q in qs]
        return qs

    validate(module.compile())

def test_list_iter(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy(module)
    def owned_arg() -> list[qubit]:
        qs = [qubit() for _ in [0,1,2]]
        qs = [h(q) for q in qs]
        return qs

    validate(module.compile())


def test_non_terminating(validate):
    module = GuppyModule("test")
    module.load_all(quantum_functional)
    module.load(qubit)

    @guppy(module)
    def test() -> None:
        q = qubit()
        while True:
            q = h(q)

    validate(module.compile())
