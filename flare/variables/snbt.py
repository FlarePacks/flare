class snbt:
    def __init__(self, value, suffix: str = ""):
        if isinstance(value, snbt):
            self.value = value.value
            self.suffix = suffix if suffix else value.suffix
        elif isinstance(value, str) and not suffix:
            self.value = value
            self.suffix = ""
        else:
            if isinstance(value, (int, float)):
                self.value = value
            else:
                try:
                    s_val = str(value)
                    self.value = float(s_val) if "." in s_val else int(s_val)
                except ValueError:
                    self.value = value
            self.suffix = suffix

    def __str__(self):
        return f"{self.value}{self.suffix}"

    def __repr__(self):
        return f"snbt({self.value!r}, {self.suffix!r})" if self.suffix else f"snbt({self.value!r})"

    def _val(self, other):
        if isinstance(other, snbt):
            return other.value
        return other

    def _binary_op(self, other, op_fn):
        v1 = self.value
        v2 = self._val(other)
        res = op_fn(v1, v2)
        s = self.suffix or (other.suffix if isinstance(other, snbt) else "")
        return snbt(res, s)

    def _rbinary_op(self, other, op_fn):
        v1 = self._val(other)
        v2 = self.value
        res = op_fn(v1, v2)
        s = self.suffix or (other.suffix if isinstance(other, snbt) else "")
        return snbt(res, s)

    def __add__(self, other):
        return self._binary_op(other, lambda a, b: a + b)

    def __radd__(self, other):
        return self._rbinary_op(other, lambda a, b: a + b)

    def __sub__(self, other):
        return self._binary_op(other, lambda a, b: a - b)

    def __rsub__(self, other):
        return self._rbinary_op(other, lambda a, b: a - b)

    def __mul__(self, other):
        return self._binary_op(other, lambda a, b: a * b)

    def __rmul__(self, other):
        return self._rbinary_op(other, lambda a, b: a * b)

    def __truediv__(self, other):
        return self._binary_op(other, lambda a, b: a / b)

    def __rtruediv__(self, other):
        return self._rbinary_op(other, lambda a, b: a / b)

    def __floordiv__(self, other):
        return self._binary_op(other, lambda a, b: a // b)

    def __rfloordiv__(self, other):
        return self._rbinary_op(other, lambda a, b: a // b)

    def __mod__(self, other):
        return self._binary_op(other, lambda a, b: a % b)

    def __rmod__(self, other):
        return self._rbinary_op(other, lambda a, b: a % b)

    def __pow__(self, other):
        return self._binary_op(other, lambda a, b: a ** b)

    def __rpow__(self, other):
        return self._rbinary_op(other, lambda a, b: a ** b)

    def __neg__(self):
        return snbt(-self.value, self.suffix)

    def __pos__(self):
        return snbt(+self.value, self.suffix)

    def __abs__(self):
        return snbt(abs(self.value), self.suffix)

    def __and__(self, other):
        return self._binary_op(other, lambda a, b: a & b)

    def __rand__(self, other):
        return self._rbinary_op(other, lambda a, b: a & b)

    def __or__(self, other):
        return self._binary_op(other, lambda a, b: a | b)

    def __ror__(self, other):
        return self._rbinary_op(other, lambda a, b: a | b)

    def __xor__(self, other):
        return self._binary_op(other, lambda a, b: a ^ b)

    def __rxor__(self, other):
        return self._rbinary_op(other, lambda a, b: a ^ b)

    def __invert__(self):
        return snbt(~self.value, self.suffix)

    def __lshift__(self, other):
        return self._binary_op(other, lambda a, b: a << b)

    def __rshift__(self, other):
        return self._binary_op(other, lambda a, b: a >> b)

    def __eq__(self, other):
        if isinstance(other, snbt):
            return self.value == other.value and self.suffix == other.suffix
        return self.value == other

    def __ne__(self, other):
        return not (self == other)

    def __lt__(self, other):
        return self.value < self._val(other)

    def __le__(self, other):
        return self.value <= self._val(other)

    def __gt__(self, other):
        return self.value > self._val(other)

    def __ge__(self, other):
        return self.value >= self._val(other)

    def __int__(self):
        return int(self.value)

    def __float__(self):
        return float(self.value)

    def __hash__(self):
        return hash((self.value, self.suffix))


_snbt = snbt
