from __future__ import annotations

from typing import Any
from .nbt import nbt


class _Storage:
    def __str__(self):
        return "storage"

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        return nbt(addr=f"storage {name}", datatype=None)

    def __setattr__(self, name, value):
        target = getattr(self, name)
        target[...] = value

    def __getitem__(self, item):
        return nbt(addr=f"storage {item}", datatype=None)

    def __setitem__(self, key, value):
        target = self[key]
        target[...] = value

    def __call__(self, item):
        return self[item]


class storage_scope:
    """Context manager that scopes relative NBT path accesses to a target storage address."""

    def __init__(self, target: str):
        self._target = target[len("storage "):] if target.startswith("storage ") else target

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def __with__(self, body_func):
        body_func()

    def __as_var__(self):
        return self

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        return nbt(addr=f"storage {self._target} {name}", datatype=None)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
            return
        target = getattr(self, name)
        target[...] = value

    def __getitem__(self, item: Any) -> Any:
        return nbt(addr=f"storage {self._target} {item}", datatype=None)

    def __setitem__(self, key: Any, value: Any) -> None:
        target = self[key]
        target[...] = value
