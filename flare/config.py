from dataclasses import dataclass
from typing import Dict, Any, Optional, Literal

ValidationMode = Literal["none", "warning", "strict"]
SchemaMode = Literal["ignore", "warning", "error", "strict", "none"]

VALIDATION_MODES = {"none", "warning", "strict"}
SCHEMA_MODES = {"ignore", "warning", "error", "strict", "none"}

VALIDATION_FIELDS = {"validation_level": ("strict", VALIDATION_MODES),
    "system_command_validation": ("none", VALIDATION_MODES), "type_narrowing": ("warning", VALIDATION_MODES),
    "nbt_schema_missing": ("error", SCHEMA_MODES), }


@dataclass
class FlareConfig:
    validation_level: str = "strict"
    system_command_validation: str = "none"
    type_narrowing: str = "warning"
    nbt_schema_missing: str = "error"
    minecraft_version: str = "1.20.4"
    namespace: str = "flare"
    pack_format: int = 15
    description: str = "A Flare datapack"
    out_dir: Optional[str] = None
    no_cache: bool = False

    def validate_and_normalize(self):
        for field_name, (default_val, valid_set) in VALIDATION_FIELDS.items():
            val = getattr(self, field_name)
            if val not in valid_set:
                raise ValueError(f"Invalid {field_name} '{val}'. Must be one of {sorted(valid_set)}.")

    def apply_to_context(self, ctx=None):
        if ctx is None:
            from . import context as ctx
        ctx.validation_level = self.validation_level
        ctx.system_command_validation = self.system_command_validation
        ctx.type_narrowing = self.type_narrowing
        ctx.nbt_schema_missing = self.nbt_schema_missing
        ctx.minecraft_version = self.minecraft_version
        ctx.config = self.to_dict()

    def update(self, overrides: Dict[str, Any]):
        for k, v in overrides.items():
            if v is not None and hasattr(self, k):
                setattr(self, k, v)
        self.validate_and_normalize()

    def to_dict(self) -> Dict[str, Any]:
        return {"validation_level": self.validation_level, "system_command_validation": self.system_command_validation,
            "type_narrowing": self.type_narrowing, "nbt_schema_missing": self.nbt_schema_missing,
            "minecraft_version": self.minecraft_version, "namespace": self.namespace, "pack_format": self.pack_format,
            "description": self.description, "no_cache": self.no_cache, }


def load_config(raw_dict: Optional[Dict[str, Any]] = None, overrides: Optional[Dict[str, Any]] = None) -> FlareConfig:
    cfg = FlareConfig()
    if raw_dict:
        cfg.update(raw_dict)
    if overrides:
        cfg.update(overrides)
    cfg.validate_and_normalize()
    return cfg
