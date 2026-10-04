import sys
from .generated import *  # noqa
from .variables.nbt import nbt as _nbt


class _NBTModule(sys.modules[__name__].__class__):
    def __call__(self, *args, **kwargs):
        return _nbt(*args, **kwargs)

    def __getitem__(self, item):
        return _nbt[item]

    def __getattr__(self, item):
        return getattr(_nbt, item)


sys.modules[__name__].__class__ = _NBTModule
