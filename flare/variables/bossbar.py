from __future__ import annotations

import json
from typing import Any, Optional, Union

from .core import addr
from .score import score
from .selector import selector
from .. import context as ctx
from ..context import _runcmd


class Bossbar:
    """Manages a Minecraft bossbar with automatic initialization and variable binding."""

    def __init__(
        self,
        bar_id: str,
        title: Union[str, dict] = "",
        *,
        color: str = "white",
        style: str = "progress",
        max_value: int = 100,
        value: int = 100,
        visible: bool = True,
        players: Optional[Union[str, selector]] = None,
    ):
        self.id = bar_id if ":" in bar_id else f"{ctx._current_namespace}:{bar_id}"
        self._title = title or bar_id

        # Format title text component
        if isinstance(self._title, str):
            title_json = json.dumps({"text": self._title})
        elif isinstance(self._title, dict):
            title_json = json.dumps(self._title)
        elif hasattr(self._title, "__print__"):
            title_json = json.dumps(self._title.__print__())
        else:
            title_json = json.dumps({"text": str(self._title)})

        # Ensure bossbar add command in load / constants
        load_file = f"{ctx._current_namespace}:__constants__"
        if load_file not in ctx.files:
            ctx.files[load_file] = []
        add_cmd = f"bossbar add {self.id} {title_json}"
        if add_cmd not in ctx.files[load_file]:
            ctx.files[load_file].append(add_cmd)

        if color != "white":
            _runcmd(f"bossbar set {self.id} color {color}")
        if style != "progress":
            _runcmd(f"bossbar set {self.id} style {style}")
        if max_value != 100:
            self.max_value = max_value
        if value != 100:
            self.value = value
        if not visible:
            _runcmd(f"bossbar set {self.id} visible false")
        if players is not None:
            self.set_players(players)

    def set_players(self, targets: Union[str, selector]) -> None:
        _runcmd(f"bossbar set {self.id} players {targets}")

    @property
    def value(self):
        return self

    @value.setter
    def value(self, val: Union[int, score, Any]) -> None:
        if isinstance(val, score):
            _runcmd(f"execute store result bossbar {self.id} value run scoreboard players get {addr(val)}")
        elif isinstance(val, int):
            _runcmd(f"bossbar set {self.id} value {val}")
        elif hasattr(val, "_addr"):
            _runcmd(f"execute store result bossbar {self.id} value run scoreboard players get {addr(val)}")
        else:
            _runcmd(f"bossbar set {self.id} value {int(val)}")

    @property
    def max_value(self):
        return self

    @max_value.setter
    def max_value(self, val: Union[int, score, Any]) -> None:
        if isinstance(val, score):
            _runcmd(f"execute store result bossbar {self.id} max run scoreboard players get {addr(val)}")
        elif isinstance(val, int):
            _runcmd(f"bossbar set {self.id} max {val}")
        elif hasattr(val, "_addr"):
            _runcmd(f"execute store result bossbar {self.id} max run scoreboard players get {addr(val)}")
        else:
            _runcmd(f"bossbar set {self.id} max {int(val)}")

    def set_visible(self, visible: bool) -> None:
        val_str = "true" if visible else "false"
        _runcmd(f"bossbar set {self.id} visible {val_str}")

    def set_color(self, color: str) -> None:
        _runcmd(f"bossbar set {self.id} color {color}")

    def set_style(self, style: str) -> None:
        _runcmd(f"bossbar set {self.id} style {style}")

    def remove(self) -> None:
        _runcmd(f"bossbar remove {self.id}")
