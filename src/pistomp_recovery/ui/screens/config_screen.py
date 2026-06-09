from __future__ import annotations

import pygame

from pistomp_recovery.facets.base import Facet
from pistomp_recovery.facets.config_facet import ConfigFacet
from pistomp_recovery.facets.packages_facet import PackagesFacet
from pistomp_recovery.facets.pedalboards_facet import PedalboardsFacet
from pistomp_recovery.facets.system_facet import SystemFacet
from pistomp_recovery.ui.colors import COLORS
from pistomp_recovery.ui.widgets.menu import Menu
from pistomp_recovery.ui.widgets.misc import Box, InputEvent
from pistomp_recovery.ui.widgets.paint import PaintContext
from pistomp_recovery.ui.widgets.text import StatusLine


class ConfigScreen:
    def __init__(self, surface: pygame.Surface) -> None:
        self._surface: pygame.Surface = surface
        self._facets: dict[str, Facet] = {
            "config": ConfigFacet(),
            "pedalboards": PedalboardsFacet(),
            "packages": PackagesFacet(),
            "system": SystemFacet(),
        }
        self._menu: Menu = Menu(Box(4, 4, 312, 200), title="Config")
        self._status: StatusLine = StatusLine(Box(4, 210, 312, 22))
        self._detail_facet: str | None = None
        self._populate_menu()

    def _populate_menu(self) -> None:
        self._menu.clear_items()
        for name, facet in self._facets.items():
            last: str | None = facet.last_stamp()
            stamp_text: str = last.split("/")[-1] if last else "never"
            self._menu.add_item(
                f"{name} (stamp: {stamp_text})",
                lambda: self._select_facet(name),
            )
        self._menu.add_item("← Back", lambda: None)

    def _select_facet(self, name: str) -> None:
        self._detail_facet = name
        self._menu.clear_items()
        self._menu.add_item(f"Stamp {name}", lambda: self._stamp(name))
        self._menu.add_item(f"Rollback {name}", lambda: self._rollback(name))
        self._menu.add_item(f"Factory reset {name}", lambda: self._factory_reset(name))
        self._menu.add_item("← Back", lambda: self._back_to_list())

    def _stamp(self, name: str) -> None:
        facet: Facet = self._facets[name]
        try:
            facet.init()
            tag: str = facet.stamp()
            self._status.set_text(f"Stamped: {tag.split('/')[-1]}", COLORS["text_success"])
        except Exception as e:
            self._status.set_text(f"Error: {e}", COLORS["text_error"])

    def _rollback(self, name: str) -> None:
        facet: Facet = self._facets[name]
        try:
            facet.init()
            facet.rollback()
            self._status.set_text(f"Rolled back {name}", COLORS["text_success"])
        except Exception as e:
            self._status.set_text(f"Error: {e}", COLORS["text_error"])

    def _factory_reset(self, name: str) -> None:
        facet: Facet = self._facets[name]
        try:
            facet.init()
            facet.factory_reset()
            self._status.set_text(f"Factory reset {name}", COLORS["text_success"])
        except Exception as e:
            self._status.set_text(f"Error: {e}", COLORS["text_error"])

    def _back_to_list(self) -> None:
        self._detail_facet = None
        self._populate_menu()

    def draw(self) -> None:
        self._surface.fill(COLORS["bg"])
        ctx: PaintContext = PaintContext(
            self._surface, Box(0, 0, 320, 240), Box(0, 0, 320, 240)
        )
        self._menu.draw(ctx)
        self._status.draw(ctx)

    def handle_event(self, event: InputEvent) -> bool:
        if event == InputEvent.LONG_CLICK:
            if self._detail_facet is not None:
                self._back_to_list()
                return True
            return False
        return self._menu.handle_event(event)
