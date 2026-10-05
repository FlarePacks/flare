from __future__ import annotations

from typing import Callable, Optional, Any

from . import context as ctx
from .context import _runcmd, push_context, get_generated_func_name
from .variables.selector import selector
from .variables.block import block


def raycast(
    step: float = 0.25,
    max_distance: float = 30.0,
    *,
    on_step: Optional[Callable[[], Any]] = None,
    on_hit_entity: Optional[Callable[[selector], Any]] = None,
    on_hit_block: Optional[Callable[[block], Any]] = None,
    stop_on_hit: bool = True,
    entity_selector: str = "@e[type=!player,dx=0,dy=0,dz=0,limit=1]",
    passable_blocks: str = "#minecraft:air",
) -> None:
    """Emits an optimized recursive Minecraft raycasting loop."""
    max_steps = max(1, int(round(max_distance / step)))
    step_id = ctx.next_func_id()
    step_func = ctx.get_generated_func_name("raycast_step")
    dist_counter = f"#ray_dist_{step_id} __flare__temp__"

    ctx.ensure_objective("__flare__temp__")
    _runcmd(f"scoreboard players set {dist_counter} 0")

    with push_context(step_func):
        _runcmd(f"scoreboard players add {dist_counter} 1")

        if on_step is not None:
            on_step()

        if on_hit_entity is not None:
            entity_hit_func = ctx.get_generated_func_name("raycast_hit_entity")
            with push_context(entity_hit_func):
                on_hit_entity(selector("@s"))
                if stop_on_hit:
                    _runcmd("return 1")

            _runcmd(f"execute as {entity_selector} at @s run function {entity_hit_func}")

        if on_hit_block is not None or stop_on_hit:
            block_hit_func = ctx.get_generated_func_name("raycast_hit_block")
            with push_context(block_hit_func):
                if on_hit_block is not None:
                    on_hit_block(block("~ ~ ~"))
                if stop_on_hit:
                    _runcmd("return 1")

            _runcmd(f"execute unless block ~ ~ ~ {passable_blocks} run function {block_hit_func}")

        # Recurse forward
        _runcmd(f"execute if score {dist_counter} matches ..{max_steps} positioned ^ ^ ^{step:g} run function {step_func}")

    # Launch initial step
    _runcmd(f"execute positioned ^ ^ ^{step:g} run function {step_func}")
