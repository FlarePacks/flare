from __future__ import annotations

from enum import Enum
from typing import Any, Optional, Type

from .score import score
from .core import addr
from .. import context as ctx


class StateEnum(Enum):
    """Base class for discrete Flare states."""
    pass


class state(score):
    """A scoreboard-backed discrete state variable bound to a StateEnum."""

    def __init__(self, enum_val: Any = None, *, addr: Optional[str] = None, multiplier: float = 1.0, **kwargs):
        if isinstance(enum_val, StateEnum):
            self._enum_cls: Optional[Type[StateEnum]] = type(enum_val)
            self._current_enum: Optional[StateEnum] = enum_val
            target_addr = addr or f"#{self._enum_cls.__name__.lower()} __{ctx._current_namespace}__state__"
            val = enum_val.value
        else:
            self._enum_cls = getattr(enum_val, "_enum_cls", None)
            self._current_enum = getattr(enum_val, "_current_enum", None)
            target_addr = addr
            val = enum_val

        super().__init__(val, addr=target_addr, multiplier=multiplier)

    def __icopy__(self, varid: str, is_recursive: bool = False):
        if self._addr is None:
            return super().__icopy__(varid, is_recursive=is_recursive)
        dest = state(addr=ctx.get_score_var_addr(varid), multiplier=self._multiplier)
        dest._enum_cls = self._enum_cls
        dest._current_enum = self._current_enum
        dest[...] = self
        return dest

    def __iset__(self, other: Any) -> state:
        if isinstance(other, StateEnum):
            if self._enum_cls is not None and not isinstance(other, self._enum_cls):
                raise TypeError(f"Cannot assign state of type {type(other).__name__} to {self._enum_cls.__name__}")
            if self._enum_cls is None:
                self._enum_cls = type(other)
            self._current_enum = other
            return super().__iset__(other.value)
        return super().__iset__(other)

    def __eq__(self, other: Any) -> Any:
        if isinstance(other, StateEnum):
            if self._enum_cls is not None and not isinstance(other, self._enum_cls):
                return False
            return super().__eq__(other.value)
        return super().__eq__(other)

    def __ne__(self, other: Any) -> Any:
        if isinstance(other, StateEnum):
            if self._enum_cls is not None and not isinstance(other, self._enum_cls):
                return True
            return super().__ne__(other.value)
        return super().__ne__(other)

    def __str__(self):
        cls_name = self._enum_cls.__name__ if self._enum_cls else "State"
        val_name = self._current_enum.name if self._current_enum else str(self._addr)
        return f"[State {cls_name}.{val_name} ({addr(self)})]"

    def __repr__(self):
        cls_name = self._enum_cls.__name__ if self._enum_cls else "State"
        val_name = self._current_enum.name if self._current_enum else str(self._addr)
        return f"state({cls_name}.{val_name})"
