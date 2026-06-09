from __future__ import annotations

from typing import Callable

import pygame

from pistomp_recovery.ui.colors import COLORS
from pistomp_recovery.ui.fonts import SIZES, get_font
from pistomp_recovery.ui.screens import Screen
from pistomp_recovery.ui.widgets.menu import Menu
from pistomp_recovery.ui.widgets.misc import Box, InputEvent
from pistomp_recovery.ui.widgets.paint import PaintContext
from pistomp_recovery.ui.widgets.text import ProgressBar, StatusLine


class UpdatesScreen(Screen):
    def __init__(
        self,
        surface: pygame.Surface,
        updates: list[tuple[str, str, str]],
        on_install: Callable[[list[str]], None] | None = None,
        on_install_single: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(surface)
        self._updates: list[tuple[str, str, str]] = updates
        self._on_install: Callable[[list[str]], None] | None = on_install
        self._on_install_single: Callable[[str], None] | None = on_install_single
        self._menu: Menu = Menu(Box(4, 24, 312, 180), title="Updates")
        self._progress: ProgressBar = ProgressBar(Box(20, 80, 280, 30))
        self._status: StatusLine = StatusLine(Box(4, 210, 312, 22))
        self._detail_pkg: str | None = None
        self._state: str = "list"
        self._build_menu()

    def _build_menu(self) -> None:
        self._menu.clear_items()
        if self._updates:
            for pkg, old_ver, new_ver in self._updates:
                self._menu.add_item(
                    f"{pkg} {old_ver} \u2192 {new_ver}",
                    lambda p=pkg: self._select_package(p),
                )
            self._menu.add_item("Update All", self._install_all)
        else:
            self._menu.add_item("No updates available", lambda: None)
        self._menu.add_item("\u2190 Back", self._go_back)

    def _select_package(self, pkg: str) -> None:
        self._detail_pkg = pkg
        self._build_detail_menu(pkg)

    def _build_detail_menu(self, pkg: str) -> None:
        self._menu.clear_items()
        old_ver: str = ""
        new_ver: str = ""
        for p, o, n in self._updates:
            if p == pkg:
                old_ver = o
                new_ver = n
                break
        self._menu.add_item(
            f"Update {pkg}", lambda: self._install_single(pkg)
        )
        self._menu.add_item(
            f"  {old_ver} \u2192 {new_ver}", lambda: None
        )
        self._menu.add_item("\u2190 Back", self._back_to_list)

    def _install_single(self, pkg: str) -> None:
        if self._on_install_single:
            self._on_install_single(pkg)

    def _install_all(self) -> None:
        if self._on_install:
            packages: list[str] = [pkg for pkg, _, _ in self._updates]
            self._on_install(packages)

    def _back_to_list(self) -> None:
        self._detail_pkg = None
        self._build_menu()

    def set_state(
        self, state: str, progress: float = 0.0, text: str = ""
    ) -> None:
        self._state = state
        self._progress.set_progress(progress)
        if text:
            color = COLORS["text_dim"]
            if state == "done":
                color = COLORS["text_success"]
            elif state == "error":
                color = COLORS["text_error"]
            elif state in (
                "downloading", "installing",
                "health_check", "stamping",
            ):
                color = COLORS["text_accent"]
            self._status.set_text(text, color)

    def draw(self) -> None:
        self._surface.fill(COLORS["bg"])

        if self._state in (
            "downloading", "installing",
            "health_check", "stamping", "rolling_back",
        ):
            title_font = get_font(SIZES["title"])
            title_text: str = {
                "downloading": "Downloading...",
                "installing": "Installing...",
                "health_check": "Verifying...",
                "stamping": "Saving snapshot...",
                "rolling_back": "Rolling back...",
            }.get(self._state, "Working...")
            title_surf: pygame.Surface = title_font.render(
                title_text, True, COLORS["text_bright"]
            )
            title_rect: pygame.Rect = title_surf.get_rect(
                centerx=160, y=30
            )
            self._surface.blit(title_surf, title_rect)

            ctx: PaintContext = PaintContext(
                self._surface, Box(0, 0, 320, 240),
                Box(0, 0, 320, 240),
            )
            self._progress.draw(ctx)
            self._status.draw(ctx)
            return

        ctx: PaintContext = PaintContext(
            self._surface, Box(0, 0, 320, 240),
            Box(0, 0, 320, 240),
        )
        self._menu.draw(ctx)
        self._status.draw(ctx)

    def handle_event(self, event: InputEvent) -> bool:
        if event == InputEvent.LONG_CLICK:
            if self._detail_pkg is not None:
                self._back_to_list()
                return True
            return False
        return self._menu.handle_event(event)
