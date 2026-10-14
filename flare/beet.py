from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

from beet import Context, configurable
from beet.core.utils import FileSystemPath
from beet.toolchain.config import load_config, locate_config
from pydantic import BaseModel

from .cli import build_datapack, EmulatorRunner


class FlareOptions(BaseModel):
    class Config:
        arbitrary_types_allowed = True
        extra = "allow"

    path: Optional[FileSystemPath] = None
    namespace: Optional[str] = None
    pack_format: Optional[int] = None
    description: Optional[str] = None
    validation: Optional[Literal["none", "warning", "strict"]] = None
    system_command_validation: Optional[Literal["none", "warning", "strict"]] = None
    minecraft_version: Optional[str] = None
    type_narrowing: Optional[Literal["none", "warning", "strict"]] = None
    nbt_schema_missing: Optional[Literal["ignore", "warning", "error", "strict", "none"]] = None
    optimize: Optional[bool] = None
    no_cache: Optional[bool] = None


def beet_default(ctx: Context) -> None:
    ctx.require(flare)


@configurable(validator=FlareOptions)
def flare(ctx: Context, opts: FlareOptions) -> None:
    if getattr(opts, "path", None):
        entry = (ctx.directory / opts.path).resolve()
    else:
        entry = _find_entry(ctx)

    if not entry.exists():
        raise FileNotFoundError(f"Flare entry-point not found: {entry}\n"
                                "Add a load path to data_pack.load, or set 'path' under meta.flare.")

    cli_overrides: dict = {}
    if ctx.project_name:
        cli_overrides["namespace"] = ctx.project_name

    root_flare_json = ctx.directory / "flare.json"
    if root_flare_json.exists() and root_flare_json != (entry.parent / "flare.json"):
        with open(root_flare_json) as fh:
            cli_overrides.update(json.load(fh))

    if getattr(opts, "namespace", None) is not None:
        cli_overrides["namespace"] = opts.namespace
    if getattr(opts, "pack_format", None) is not None:
        cli_overrides["pack_format"] = opts.pack_format
    if getattr(opts, "description", None) is not None:
        cli_overrides["description"] = opts.description
    if getattr(opts, "validation", None) is not None:
        cli_overrides["validation_level"] = opts.validation
    if getattr(opts, "system_command_validation", None) is not None:
        cli_overrides["system_command_validation"] = opts.system_command_validation
    if getattr(opts, "minecraft_version", None) is not None:
        cli_overrides["minecraft_version"] = opts.minecraft_version
    if getattr(opts, "nbt_schema_missing", None) is not None:
        cli_overrides["nbt_schema_missing"] = opts.nbt_schema_missing
    if getattr(opts, "type_narrowing", None) is not None:
        cli_overrides["type_narrowing"] = opts.type_narrowing
    if getattr(opts, "optimize", None) is not None:
        cli_overrides["optimize"] = opts.optimize
    if getattr(opts, "no_cache", None) is not None:
        cli_overrides["no_cache"] = opts.no_cache

    known_keys = {
        "path", "namespace", "pack_format", "description", "validation",
        "system_command_validation", "minecraft_version", "nbt_schema_missing",
        "type_narrowing", "optimize", "no_cache",
    }
    extra_opts = {}
    dump_method = getattr(opts, "dict", None) or getattr(opts, "model_dump", None)
    model_data = dump_method(exclude_unset=True) if dump_method else {}
    for key, value in model_data.items():
        if key not in known_keys:
            extra_opts[key] = value

    for key, value in extra_opts.items():
        if key != "run":
            cli_overrides[key] = value

    success, _watch_files, _ = build_datapack(str(entry), cli_overrides, beet_ctx=ctx)

    if not success:
        raise RuntimeError(f"Flare compilation failed for entry-point: {entry}")

    if "run" in extra_opts:
        run_val = extra_opts["run"]
        runner = EmulatorRunner(str(entry), run_val)
        if runner.start():
            runner.wait()


def _find_entry(ctx: Context) -> Path:
    candidates: list[Path] = []

    default_names = ["main.fl", "main.py"]
    flare_json_path = ctx.directory / "flare.json"
    if flare_json_path.exists():
        try:
            with open(flare_json_path) as f:
                data = json.load(f)
                if "input" in data:
                    default_names.insert(0, data["input"])
        except Exception:
            pass

    try:
        config = load_config(locate_config(ctx.directory, parents=True))
        for item in config.data_pack.load.entries():
            if isinstance(item, dict):
                continue
            item_path = str(item)
            if Path(item_path).is_absolute():
                load_dir = Path(item_path)
            else:
                load_dir = ctx.directory / item_path

            if load_dir.is_dir():
                candidates.append(load_dir)
    except Exception:
        pass

    candidates.append(ctx.directory)

    for directory in candidates:
        for name in default_names:
            candidate = directory / name
            if candidate.exists():
                return candidate

    return ctx.directory / default_names[0]
