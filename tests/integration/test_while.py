from guppy.decorator import guppy


def test_infinite_loop(validate):
    @guppy(compile=True)
    def foo() -> int:
        while True:
            pass
        return 0

    validate(foo)


def test_counting_loop(validate):
    @guppy(compile=True)
    def foo(i: int) -> int:
        while i > 0:
            i -= 1
        return 0

    validate(foo)


def test_break(validate):
    @guppy(compile=True)
    def foo(i: int) -> int:
        while True:
            if i == 0:
                break
            i -= 1
        return 0

    validate(foo)


def test_continue(validate):
    @guppy(compile=True)
    def foo(i: int) -> int:
        x = 42
        while True:
            if i % 2 == 0:
                continue
            x = x + i
        return x

    validate(foo)


def test_return_in_loop(validate):
    @guppy(compile=True)
    def foo(i: int) -> int:
        x = 42
        while i > 0:
            if x >= 1337:
                return x + i
            x = x + i
            i -= 1
        return x

    validate(foo)


def test_nested_loop(validate):
    @guppy(compile=True)
    def foo(x: int, y: int) -> int:
        p = 0
        while x > 0:
            s = 0
            while y > 0:
                s += x
                y -= 1
            p += s
            x -= 1
        return p

    validate(foo)


def test_nested_loop_break_continue(validate):
    @guppy(compile=True)
    def foo(x: int, y: int) -> int:
        p = 0
        while x > 0:
            s = 0
            while True:
                if x % 2 == 0:
                    continue
                s += x
                if s > y:
                    s = y
                else:
                    break
                y -= 1
            p += s
            x -= 1
        return p

    validate(foo)
