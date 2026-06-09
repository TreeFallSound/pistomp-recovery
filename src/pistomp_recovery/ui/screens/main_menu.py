from __future__ import annotations

from typing import Callable

import pygame

from pistomp_recovery.ui.colors import COLORS
from pistomp_recovery.ui.screens import Screen
from pistomp_recovery.ui.screens.types import Actions
from pistomp_recovery.ui.widgets.menu import Menu
from pistomp_recovery.ui.widgets.misc import Box, InputEvent
from pistomp_recovery.ui.widgets.paint import PaintContext


class MainMenuScreen(Screen):
    def __init__(
        self,
        surface: pygame.Surface,
        actions: Actions,
        dirty_count: int = 0,
        update_count: int = 0,
    ) -> None:
        super().__init__(surface)
        self._menu: Menu = Menu(Box(4, 4, 312, 232), title="Recovery")
        self._actions: Actions = actions
        self._dirty_count: int = dirty_count
        self._update_count: int = update_count
        self._build_menu()

    def _build_menu(self) -> None:
        self._menu.clear_items()
        self._menu.add_item("Resume", self._action("resume"))

        if self._dirty_count > 0:
            self._menu.add_item("Reset...", self._action("reset"), f"{self._dirty_count} changed")
        if self._update_count > 0:
            self._menu.add_item(
                "Update...", self._action("update"), f"{self._update_count} available"
            )

        self._menu.add_item("Pedalboards...", self._action("pedalboards"))
        self._menu.add_item("Packages...", self._action("packages"))
        self._menu.add_item("System Info...", self._action("system_info"))
        self._menu.add_item("Reboot", self._action("reboot"))
        self._menu.add_item("Power Off", self._action("power_off"))

    def _action(self, name: str) -> Callable[[], None]:
        return self._actions.get(name, lambda: None)

    def update_counts(self, dirty_count: int, update_count: int) -> None:
        self._dirty_count = dirty_count
        self._update_count = update_count
        self._build_menu()

    def draw(self) -> None:
        self._surface.fill(COLORS["bg"])
        ctx: PaintContext = PaintContext(self._surface, Box(0, 0, 320, 240), Box(0, 0, 320, 240))
        self._menu.draw(ctx)

    def handle_event(self, event: InputEvent) -> bool:
        if event == InputEvent.LONG_CLICK:
            return False
        return self._menu.handle_event(event)
