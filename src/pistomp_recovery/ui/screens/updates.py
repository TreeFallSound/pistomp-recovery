from __future__ import annotations

import pygame

from pistomp_recovery.packages.manager import PackageManager
from pistomp_recovery.ui.colors import COLORS
from pistomp_recovery.ui.widgets.menu import Menu
from pistomp_recovery.ui.widgets.misc import Box, InputEvent
from pistomp_recovery.ui.widgets.text import StatusLine


class UpdatesScreen:
    def __init__(self, surface: pygame.Surface, pkg_manager: PackageManager) -> None:
        self._surface: pygame.Surface = surface
        self._pkg_manager: PackageManager = pkg_manager
        self._updates: list[tuple[str, str, str]] = []
        self._menu: Menu = Menu(Box(4, 24, 312, 180), title="Updates")
        self._status: StatusLine = StatusLine(Box(4, 210, 312, 22))
        self._state: str = "checking"
        self._has_updates: bool = False

    def check_updates(self) -> None:
        self._status.set_text("Checking for updates...", COLORS["text_accent"])
        try:
            self._updates = self._pkg_manager.check_updates()
            self._has_updates = len(self._updates) > 0
        except Exception as e:
            self._status.set_text(f"Error: {e}", COLORS["text_error"])
            self._state = "error"
            return

        self._menu.clear_items()
        if self._has_updates:
            for pkg, old_ver, new_ver in self._updates:
                self._menu.add_item(
                    f"{pkg} {old_ver} → {new_ver}",
                    lambda p=pkg: self._select_package(p),
                )
            self._menu.add_item("Install All", lambda _: self._install_all())
            self._menu.add_item("← Back", lambda _: None)
            self._status.set_text(
                f"{len(self._updates)} updates available",
                COLORS["text_success"],
            )
            self._state = "available"
        else:
            self._menu.add_item("No updates available", lambda _: None)
            self._menu.add_item("← Back", lambda _: None)
            self._status.set_text("System is up to date", COLORS["text_success"])
            self._state = "none"

    def _select_package(self, package: str) -> None:
        pass

    def _install_all(self) -> None:
        packages: list[str] = [pkg for pkg, _, _ in self._updates]
        self._status.set_text("Downloading...", COLORS["text_accent"])
        if not self._pkg_manager.download_packages(packages):
            self._status.set_text("Download failed", COLORS["text_error"])
            return
        self._status.set_text("Installing...", COLORS["text_accent"])
        if not self._pkg_manager.install_packages(packages):
            self._status.set_text("Install failed", COLORS["text_error"])
            return
        self._status.set_text("Update complete", COLORS["text_success"])
        self._state = "done"

    def draw(self) -> None:
        self._surface.fill(COLORS["bg"])
        ctx: pygame.Rect = pygame.Rect(0, 0, 320, 240)
        self._menu.draw(ctx)
        self._status.draw(ctx)

    def handle_event(self, event: InputEvent) -> bool:
        if event == InputEvent.LONG_CLICK:
            return False
        return self._menu.handle_event(event)
