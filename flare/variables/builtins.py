import builtins
import string
from math import inf


def addr(var):
    return var._addr


class flare_len:
    def __new__(cls, x):
        if hasattr(x, "__len__"):
            return x.__len__()
        return builtins.len(x)


from .core import FlareClassMeta


class fail(metaclass=FlareClassMeta):
    pass


_FailType = fail


class IntReturn:
    def __init__(self, func_name):
        self.func_name = func_name

    def __icopy__(self, varid=None, is_recursive=False):
        return self


class flare_range:
    def __init__(self, *args):
        from .score import score
        from .core import FlareValue

        self.args = args
        self.is_flare = any(isinstance(a, FlareValue) for a in args)
        if not self.is_flare:
            self._native = builtins.range(*args)
        else:
            self._args = [a if isinstance(a, FlareValue) else score(a) for a in args]

    def __iter__(self):
        if not self.is_flare:
            return iter(self._native)
        raise TypeError("Cannot iterate over a dynamic scoreboard range in Python.")

    def __in__(self, item):
        if hasattr(item, "__rin__"):
            return item.__rin__(self)
        return NotImplemented

    def __contains__(self, item):
        res = self.__in__(item)
        if res is not NotImplemented:
            return res
        return False

    def __for__(self, body_func, orelse_func=None, has_break=False, has_continue=False):
        from ..control_flow import _flare_for
        from .. import context as ctx
        from .score import score
        from ..control_flow import _flare_while

        if not self.is_flare:
            return _flare_for(self._native, body_func, orelse_func, has_break, has_continue)

        start = score(0)
        step = score(1)
        if len(self._args) == 1:
            stop = self._args[0]
        elif len(self._args) == 2:
            start = self._args[0]
            stop = self._args[1]
        else:
            start = self._args[0]
            stop = self._args[1]
            step = self._args[2]

        is_neg = False
        if len(self.args) == 3 and isinstance(self.args[2], (int, float)) and self.args[2] < 0:
            is_neg = True

        i = score(0, addr=f"#range_i_{ctx.next_temp_id()}")
        i[...] = start

        def loop_body():
            body_func(i)
            i.__iadd__(step)

        cond = i > stop if is_neg else i < stop
        return _flare_while(cond, loop_body, orelse_func, has_break, has_continue)


def flare_ord(s):
    from .core import FlareValue
    from ..context import _runcmd
    from .score import score
    from .. import context as ctx
    from .core import LazyOp

    if not isinstance(s, FlareValue):
        return builtins.ord(s)

    def eval_ord(dest):
        dest[...] = 0
        _id = ctx.next_temp_id()

        _runcmd(f"data modify storage flare:temp ord_char_{_id} set from {addr(s)} 0 1")

        for c in string.printable:
            safe_c = c.replace('\\', '\\\\').replace('"', '\\"')
            _runcmd(
                f"execute if data storage flare:temp {{\"ord_char_{_id}\": \"{safe_c}\"}} run scoreboard players set {addr(dest)} {builtins.ord(c)}")
        return dest

    def alloc_temp():
        return score(addr=f"#ord_out_{ctx.next_temp_id()}")

    return LazyOp(s, eval_ord, alloc_temp)


def flare_bin(n):
    from .core import FlareValue
    from ..context import _runcmd
    from .score import score
    from .nbt import nbt
    from ..types import NBTType
    from .. import context as ctx
    from ..control_flow import ScoreIfMatches
    from .core import LazyOp

    if not isinstance(n, FlareValue):
        return builtins.bin(n)

    def eval_bin(dest):
        _id = ctx.next_temp_id()
        n_score = score(0, addr=f"#bin_n_{_id}")
        n_score[...] = n

        dest[...] = ""
        func_name = ctx.get_generated_func_name("bin")

        char_temp = nbt(addr=f"flare:temp bin_char_{_id}", datatype=NBTType.String)

        def loop():
            nonlocal n_score
            modulo = score(addr=f"#bin_mod_{_id}")
            modulo[...] = n_score % 2
            ScoreIfMatches(modulo, 0).then(lambda: char_temp.__iset__("0"))
            ScoreIfMatches(modulo, 1).then(lambda: char_temp.__iset__("1"))

            dest.prepend(char_temp)

            n_score /= 2
            ScoreIfMatches(n_score, (1, inf)).then(lambda: _runcmd(f"function {func_name}"))

        with ctx.push_context(func_name):
            loop()

        ScoreIfMatches(n_score, 0).then(lambda: dest.__iset__("0"))
        ScoreIfMatches(n_score, (1, inf)).then(lambda: _runcmd(f"function {func_name}"))
        return dest

    def alloc_temp():
        return nbt(addr=f"flare:temp bin_out_{ctx.next_temp_id()}", datatype=NBTType.String)

    return LazyOp(n, eval_bin, alloc_temp)


def parse_int(s):
    from .core import FlareValue, LazyOp
    from .. import context as ctx
    from ..context import _runcmd
    from .score import score
    from .nbt import nbt
    from ..types import NBTType
    from ..control_flow import ScoreIfMatches

    if not isinstance(s, FlareValue):
        return builtins.int(s)

    def eval_parse_int(dest):
        _id = ctx.next_temp_id()
        temp_str = nbt(addr=f"flare:temp parse_curr_{_id}", datatype=NBTType.String)
        temp_str[...] = s

        str_len = score(addr=f"#parse_len_{_id}")
        _runcmd(f"execute store result score {addr(str_len)} run data get storage flare:temp parse_curr_{_id}")

        is_neg = score(0, addr=f"#parse_neg_{_id}")
        digit_val = score(addr=f"#parse_dig_{_id}")
        dest[...] = 0

        func_name = ctx.get_generated_func_name("parse_int_loop")

        def loop():
            _runcmd(f"data modify storage flare:temp parse_char_{_id} set string storage flare:temp parse_curr_{_id} 0 1")
            _runcmd(f"data modify storage flare:temp parse_curr_{_id} set string storage flare:temp parse_curr_{_id} 1")
            str_len.__isub__(1)

            _runcmd(f'execute if data storage flare:temp {{"parse_char_{_id}": "-"}} run scoreboard players set {addr(is_neg)} 1')

            digit_val[...] = -1
            for d in range(10):
                _runcmd(f'execute if data storage flare:temp {{"parse_char_{_id}": "{d}"}} run scoreboard players set {addr(digit_val)} {d}')

            ScoreIfMatches(digit_val, (0, inf)).then(lambda: dest.__imul__(10))
            ScoreIfMatches(digit_val, (0, inf)).then(lambda: dest.__iadd__(digit_val))

            ScoreIfMatches(str_len, (1, inf)).then(lambda: _runcmd(f"function {func_name}"))

        with ctx.push_context(func_name):
            loop()

        ScoreIfMatches(str_len, (1, inf)).then(lambda: _runcmd(f"function {func_name}"))
        ScoreIfMatches(is_neg, 1).then(lambda: dest.__imul__(-1))
        return dest

    def alloc_temp():
        return score(addr=f"#parse_int_out_{ctx.next_temp_id()}")

    return LazyOp(s, eval_parse_int, alloc_temp)


def parse_float(s, precision: int = 4):
    from .core import FlareValue, LazyOp
    from .. import context as ctx
    from ..context import _runcmd
    from .score import score, fixed
    from .nbt import nbt
    from ..types import NBTType
    from ..control_flow import ScoreIfMatches

    if not isinstance(s, FlareValue):
        return builtins.float(s)

    multiplier = 10 ** -precision

    def eval_parse_float(dest):
        _id = ctx.next_temp_id()
        temp_str = nbt(addr=f"flare:temp parse_curr_{_id}", datatype=NBTType.String)
        temp_str[...] = s

        str_len = score(addr=f"#parse_len_{_id}")
        _runcmd(f"execute store result score {addr(str_len)} run data get storage flare:temp parse_curr_{_id}")

        is_neg = score(0, addr=f"#parse_neg_{_id}")
        seen_dot = score(0, addr=f"#parse_dot_{_id}")
        frac_left = score(precision, addr=f"#parse_frac_{_id}")
        digit_val = score(addr=f"#parse_dig_{_id}")
        should_accumulate = score(0, addr=f"#parse_acc_{_id}")

        dest[...] = 0

        func_name = ctx.get_generated_func_name("parse_float_loop")

        def loop():
            _runcmd(f"data modify storage flare:temp parse_char_{_id} set string storage flare:temp parse_curr_{_id} 0 1")
            _runcmd(f"data modify storage flare:temp parse_curr_{_id} set string storage flare:temp parse_curr_{_id} 1")
            str_len.__isub__(1)

            _runcmd(f'execute if data storage flare:temp {{"parse_char_{_id}": "-"}} run scoreboard players set {addr(is_neg)} 1')
            _runcmd(f'execute if data storage flare:temp {{"parse_char_{_id}": "."}} run scoreboard players set {addr(seen_dot)} 1')

            digit_val[...] = -1
            for d in range(10):
                _runcmd(f'execute if data storage flare:temp {{"parse_char_{_id}": "{d}"}} run scoreboard players set {addr(digit_val)} {d}')

            ScoreIfMatches(digit_val, (0, inf)).then(lambda: (
                ScoreIfMatches(seen_dot, 0).then(lambda: should_accumulate.__iset__(1)),
                ScoreIfMatches(seen_dot, 1).then(lambda: (
                    ScoreIfMatches(frac_left, (1, inf)).then(lambda: (
                        should_accumulate.__iset__(1),
                        frac_left.__isub__(1)
                    ))
                )),
                ScoreIfMatches(should_accumulate, 1).then(lambda: (
                    dest.__imul__(10),
                    dest.__iadd__(digit_val),
                    should_accumulate.__iset__(0)
                ))
            ))

            ScoreIfMatches(str_len, (1, inf)).then(lambda: _runcmd(f"function {func_name}"))

        with ctx.push_context(func_name):
            loop()

        ScoreIfMatches(str_len, (1, inf)).then(lambda: _runcmd(f"function {func_name}"))

        # Padding loop for remaining fractional digits
        pad_func = ctx.get_generated_func_name("parse_pad_loop")

        def pad_loop():
            dest.__imul__(10)
            frac_left.__isub__(1)
            ScoreIfMatches(frac_left, (1, inf)).then(lambda: _runcmd(f"function {pad_func}"))

        with ctx.push_context(pad_func):
            pad_loop()

        ScoreIfMatches(frac_left, (1, inf)).then(lambda: _runcmd(f"function {pad_func}"))
        ScoreIfMatches(is_neg, 1).then(lambda: dest.__imul__(-1))
        return dest

    def alloc_temp():
        return fixed(addr=f"#parse_float_out_{ctx.next_temp_id()}", multiplier=multiplier)

    return LazyOp(s, eval_parse_float, alloc_temp)

