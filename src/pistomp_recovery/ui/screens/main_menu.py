from __future__ import annotations

from enum import Enum, auto

import pygame

from pistomp_recovery.ui.colors import COLORS
from pistomp_recovery.ui.widgets.menu import Menu
from pistomp_recovery.ui.widgets.misc import Box, InputEvent
from pistomp_recovery.ui.widgets.paint import PaintContext


class MenuAction(Enum):
    RESUME = auto()
    SYSTEM_INFO = auto()
    PACKAGE_UPDATES = auto()
    CONFIG_MANAGEMENT = auto()
    FACTORY_RESET = auto()
    REBOOT = auto()
    POWER_OFF = auto()


class MainMenuScreen:
    def __init__(self, surface: pygame.Surface) -> None:
        self._surface: pygame.Surface = surface
        self._menu: Menu = Menu(Box(4, 4, 312, 232), title="Recovery")
        self._action: MenuAction | None = None

        self._menu.add_item("Resume", lambda: self._set_action(MenuAction.RESUME))
        self._menu.add_item("System Info", lambda: self._set_action(MenuAction.SYSTEM_INFO))
        self._menu.add_item(
            "Package Updates",
            lambda: self._set_action(MenuAction.PACKAGE_UPDATES),
        )
        self._menu.add_item(
            "Config Management",
            lambda: self._set_action(MenuAction.CONFIG_MANAGEMENT),
        )
        self._menu.add_item("Factory Reset", lambda: self._set_action(MenuAction.FACTORY_RESET))
        self._menu.add_item("Reboot", lambda: self._set_action(MenuAction.REBOOT))
        self._menu.add_item("Power Off", lambda: self._set_action(MenuAction.POWER_OFF))

    def _set_action(self, action: MenuAction) -> None:
        self._action = action

    @property
    def action(self) -> MenuAction | None:
        return self._action

    @action.setter
    def action(self, value: MenuAction | None) -> None:
        self._action = value

    def draw(self) -> None:
        self._surface.fill(COLORS["bg"])
        ctx: PaintContext = PaintContext(
            self._surface, Box(0, 0, 320, 240), Box(0, 0, 320, 240)
        )
        self._menu.draw(ctx)

    def handle_event(self, event: InputEvent) -> bool:
        return self._menu.handle_event(event)
