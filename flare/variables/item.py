import json

from flare.generated.item_base import item_base
from flare.variables.core import FlareClassMeta


class item(item_base, metaclass=FlareClassMeta):
    def __str__(self):
        if not self.components:
            return self.id

        comp_strs = []
        for key, value in self.components.items():
            if isinstance(value, bool):
                if value:
                    comp_strs.append(key)
                else:
                    comp_strs.append(f"#{key}")
            else:
                if hasattr(value, "__print__"):
                    value = value.__print__()

                if isinstance(value, str):
                    if not (value.startswith("{") or value.startswith("[")):
                        val_str = json.dumps(value)
                    else:
                        val_str = value
                else:
                    val_str = json.dumps(value, separators=(",", ":"),
                        default=lambda x: x.__print__() if hasattr(x, "__print__") else str(x))

                comp_strs.append(f"{key}={val_str}")

        return f"{self.id}[{','.join(comp_strs)}]"


class ItemComponentsProxy:
    """Proxy providing typed access to 1.20.5+ item components in an NBT compound."""

    _KNOWN_TYPES = {
        "damage": "Int",
        "max_damage": "Int",
        "repair_cost": "Int",
        "custom_model_data": "Int",
        "custom_data": "Compound",
        "custom_name": "String",
        "item_name": "String",
        "lore": "List",
        "enchantments": "Compound",
        "food": "Compound",
        "unbreakable": "Byte",
    }

    def __init__(self, target_type: str, target: str, base_path: str):
        self._target_type = target_type
        self._target = target
        self._base_path = base_path

    def _comp_key(self, name: str) -> str:
        if name.startswith('"') and name.endswith('"'):
            return name
        if ":" in name:
            return f'"{name}"'
        return f'"minecraft:{name}"'

    def _get_comp_nbt(self, name: str):
        from .nbt import nbt
        from ..types import NBTType

        comp_key = self._comp_key(name)
        addr = f"{self._target_type} {self._target} {self._base_path}.{comp_key}"
        clean_name = name.removeprefix("minecraft:")
        type_str = self._KNOWN_TYPES.get(clean_name)
        dtype = getattr(NBTType, type_str) if type_str else None
        return nbt(addr=addr, datatype=dtype)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        return self._get_comp_nbt(name)

    def __setattr__(self, name: str, value):
        if name.startswith("_"):
            super().__setattr__(name, value)
            return
        node = self._get_comp_nbt(name)
        if node is not value:
            node[...] = value

    def __getitem__(self, item: str):
        return self._get_comp_nbt(str(item))

    def __setitem__(self, item: str, value):
        node = self._get_comp_nbt(str(item))
        if node is not value:
            node[...] = value


class ItemSlot:
    """Represents a specific item slot on an entity, block, or storage."""

    def __init__(self, target: str, path: str, slot_id: str | None = None, target_type: str = "entity"):
        self._target = str(target)
        self._path = path
        self._slot_id = slot_id
        self._target_type = target_type

    @property
    def components(self) -> ItemComponentsProxy:
        return ItemComponentsProxy(self._target_type, self._target, f"{self._path}.components")

    @property
    def id(self):
        from .nbt import nbt
        from ..types import NBTType
        return nbt(addr=f"{self._target_type} {self._target} {self._path}.id", datatype=NBTType.String)

    @property
    def count(self):
        from .nbt import nbt
        from ..types import NBTType
        return nbt(addr=f"{self._target_type} {self._target} {self._path}.count", datatype=NBTType.Byte)

    def replace(self, item_val, count: int | None = None):
        from ..context import _runcmd
        count_str = f" {count}" if count is not None and count > 1 else ""
        if self._slot_id:
            _runcmd(f"item replace {self._target_type} {self._target} {self._slot_id} with {item_val}{count_str}")
        else:
            _runcmd(f"data modify {self._target_type} {self._target} {self._path} set value {item_val}")

    def __iset__(self, other):
        self.replace(other)
        return self

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        return getattr(self.components, name)

    def __setattr__(self, name: str, value):
        if name.startswith("_") or name in ("_target", "_path", "_slot_id", "_target_type", "components", "id", "count"):
            super().__setattr__(name, value)
            return
        node = getattr(self.components, name)
        if node is not value:
            node[...] = value


class InventoryAccessor:
    """Accessor for inventory slots on an entity."""

    def __init__(self, target: str):
        self._target = str(target)

    def __getitem__(self, slot: int) -> ItemSlot:
        return ItemSlot(self._target, f"Inventory[{{Slot: {slot}b}}]", slot_id=f"container.{slot}", target_type="entity")

    def clear(self, item_name=None, max_count: int | None = None):
        from .selector import selector
        selector(self._target).clear_inventory(item_name, max_count)

    @property
    def nbt(self):
        from .nbt import nbt
        from ..types import NBTType
        return nbt(addr=f"entity {self._target} Inventory", datatype=NBTType.List)

