from __future__ import annotations

import math
from typing import Any, Optional, Union

from .core import FlareValue, addr
from .score import score
from .. import context as ctx
from ..context import _runcmd


class vec3(FlareValue):
    """A first-class 3D spatial vector with scoreboard-backed components and arithmetic."""

    def __init__(
        self,
        x: Any = 0,
        y: Any = 0,
        z: Any = 0,
        *,
        name: Optional[str] = None,
        multiplier: float = 1.0,
    ):
        self._multiplier = float(multiplier)
        prefix = name or f"#v{ctx.next_temp_id()}"

        def _wrap_comp(val, axis):
            if isinstance(val, score):
                return val
            if isinstance(val, FlareValue):
                s = score(addr=f"{prefix}_{axis}", multiplier=self._multiplier)
                s[...] = val
                return s
            return score(val, addr=f"{prefix}_{axis}", multiplier=self._multiplier)

        self.x = _wrap_comp(x, "x")
        self.y = _wrap_comp(y, "y")
        self.z = _wrap_comp(z, "z")

    def __str__(self):
        return f"[vec3 {self.x} {self.y} {self.z}]"

    def __repr__(self):
        return f"vec3({self.x}, {self.y}, {self.z})"

    def to_coords(self) -> str:
        """Returns coordinate string if values are constants, or tilde offsets."""
        return f"~{self.x} ~{self.y} ~{self.z}"

    def __iset__(self, other: Any) -> vec3:
        if isinstance(other, vec3):
            self.x[...] = other.x
            self.y[...] = other.y
            self.z[...] = other.z
            return self
        elif isinstance(other, (tuple, list)) and len(other) == 3:
            self.x[...] = other[0]
            self.y[...] = other[1]
            self.z[...] = other[2]
            return self
        raise TypeError(f"Cannot assign {type(other)} to vec3")

    def __add__(self, other: Any) -> vec3:
        if isinstance(other, vec3):
            return vec3(self.x + other.x, self.y + other.y, self.z + other.z, multiplier=self._multiplier)
        return vec3(self.x + other, self.y + other, self.z + other, multiplier=self._multiplier)

    def __radd__(self, other: Any) -> vec3:
        return self.__add__(other)

    def __sub__(self, other: Any) -> vec3:
        if isinstance(other, vec3):
            return vec3(self.x - other.x, self.y - other.y, self.z - other.z, multiplier=self._multiplier)
        return vec3(self.x - other, self.y - other, self.z - other, multiplier=self._multiplier)

    def __rsub__(self, other: Any) -> vec3:
        if isinstance(other, vec3):
            return vec3(other.x - self.x, other.y - self.y, other.z - self.z, multiplier=self._multiplier)
        return vec3(other - self.x, other - self.y, other - self.z, multiplier=self._multiplier)

    def __mul__(self, other: Any) -> vec3:
        if isinstance(other, vec3):
            return vec3(self.x * other.x, self.y * other.y, self.z * other.z, multiplier=self._multiplier)
        return vec3(self.x * other, self.y * other, self.z * other, multiplier=self._multiplier)

    def __rmul__(self, other: Any) -> vec3:
        return self.__mul__(other)

    def __truediv__(self, other: Any) -> vec3:
        if isinstance(other, vec3):
            return vec3(self.x / other.x, self.y / other.y, self.z / other.z, multiplier=self._multiplier)
        return vec3(self.x / other, self.y / other, self.z / other, multiplier=self._multiplier)

    def __rtruediv__(self, other: Any) -> vec3:
        if isinstance(other, vec3):
            return vec3(other.x / self.x, other.y / self.y, other.z / self.z, multiplier=self._multiplier)
        return vec3(other / self.x, other / self.y, other / self.z, multiplier=self._multiplier)

    def __floordiv__(self, other: Any) -> vec3:
        return self.__truediv__(other)

    def __neg__(self) -> vec3:
        return vec3(-self.x, -self.y, -self.z, multiplier=self._multiplier)

    def __iadd__(self, other: Any) -> vec3:
        if isinstance(other, vec3):
            self.x += other.x
            self.y += other.y
            self.z += other.z
        else:
            self.x += other
            self.y += other
            self.z += other
        return self

    def __isub__(self, other: Any) -> vec3:
        if isinstance(other, vec3):
            self.x -= other.x
            self.y -= other.y
            self.z -= other.z
        else:
            self.x -= other
            self.y -= other
            self.z -= other
        return self

    def __imul__(self, other: Any) -> vec3:
        if isinstance(other, vec3):
            self.x *= other.x
            self.y *= other.y
            self.z *= other.z
        else:
            self.x *= other
            self.y *= other
            self.z *= other
        return self

    def __itruediv__(self, other: Any) -> vec3:
        if isinstance(other, vec3):
            self.x /= other.x
            self.y /= other.y
            self.z /= other.z
        else:
            self.x /= other
            self.y /= other
            self.z /= other
        return self

    def dot(self, other: vec3) -> score:
        """Computes the scalar dot product between two vectors."""
        if not isinstance(other, vec3):
            raise TypeError(f"dot product requires vec3, got {type(other)}")
        return (self.x * other.x) + (self.y * other.y) + (self.z * other.z)

    def cross(self, other: vec3) -> vec3:
        """Computes the vector cross product between two vectors."""
        if not isinstance(other, vec3):
            raise TypeError(f"cross product requires vec3, got {type(other)}")
        cx = self.y * other.z - self.z * other.y
        cy = self.z * other.x - self.x * other.z
        cz = self.x * other.y - self.y * other.x
        return vec3(cx, cy, cz, multiplier=self._multiplier)

    def length_squared(self) -> score:
        """Returns the squared length (magnitude squared) of the vector."""
        return self.x * self.x + self.y * self.y + self.z * self.z

    def length(self) -> score:
        """Returns the magnitude of the vector using square root."""
        from ..math import sqrt
        return sqrt(self.length_squared())

    def distance_to(self, other: vec3) -> score:
        """Computes the Euclidean distance to another vector."""
        diff = self - other
        return diff.length()

    def normalize(self) -> vec3:
        """Returns a normalized unit vector."""
        mag = self.length()
        return self / mag

    @classmethod
    def from_entity(cls, target: Any, path: str = "Pos", scale: float = 1.0) -> vec3:
        """Extracts 3D coordinates from an entity's NBT tag into a vec3."""
        target_str = str(target)
        v = cls(multiplier=1.0)
        scale_str = f" {scale:g}" if scale != 1.0 else ""
        _runcmd(f"execute store result score {addr(v.x)} run data get entity {target_str} {path}[0]{scale_str}")
        _runcmd(f"execute store result score {addr(v.y)} run data get entity {target_str} {path}[1]{scale_str}")
        _runcmd(f"execute store result score {addr(v.z)} run data get entity {target_str} {path}[2]{scale_str}")
        return v

    def apply_to(self, target: Any, path: str = "Pos", scale: float = 1.0) -> None:
        """Stores the vector's components back into an entity's NBT array."""
        target_str = str(target)
        inv_scale = 1.0 / scale
        scale_str = f" {inv_scale:g}" if inv_scale != 1.0 else " 1.0"
        _runcmd(f"execute store result entity {target_str} {path}[0] double{scale_str} run scoreboard players get {addr(self.x)}")
        _runcmd(f"execute store result entity {target_str} {path}[1] double{scale_str} run scoreboard players get {addr(self.y)}")
        _runcmd(f"execute store result entity {target_str} {path}[2] double{scale_str} run scoreboard players get {addr(self.z)}")
