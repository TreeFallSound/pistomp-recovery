from __future__ import annotations

import pygame

from pistomp_recovery.ui.colors import COLORS
from pistomp_recovery.ui.fonts import SIZES, SafeFont, get_font
from pistomp_recovery.ui.widgets.menu import Menu
from pistomp_recovery.ui.widgets.misc import Box, InputEvent


class Screen:
    def __init__(self, display_surface: pygame.Surface) -> None:
        self._surface: pygame.Surface = display_surface

    def draw(self) -> None:
        raise NotImplementedError

    def handle_event(self, event: InputEvent) -> bool:
        return False


class CrashScreen(Screen):
    def __init__(
        self,
        display_surface: pygame.Surface,
        crash_log: str = "",
        on_resume: callable | None = None,
        on_recovery: callable | None = None,
    ) -> None:
        super().__init__(display_surface)
        self._crash_log: str = crash_log
        self._on_resume: callable | None = on_resume
        self._on_recovery: callable | None = on_recovery
        self._menu: Menu = Menu(Box(10, 40, 300, 190), title="App Crashed")
        self._menu.add_item("Resume", lambda _: self._resume())
        self._menu.add_item("Recovery Menu", lambda _: self._recovery())

    def _resume(self) -> None:
        if self._on_resume:
            self._on_resume()

    def _recovery(self) -> None:
        if self._on_recovery:
            self._on_recovery()

    def draw(self) -> None:
        self._surface.fill(COLORS["bg"])

        title_font: SafeFont = get_font(SIZES["title"])
        title_surf: pygame.Surface = title_font.render("App Crashed", True, COLORS["text_error"])
        title_rect: pygame.Rect = title_surf.get_rect(centerx=160, y=8)
        self._surface.blit(title_surf, title_rect)

        if self._crash_log:
            lines: list[str] = self._crash_log.split("\n")[-5:]
            log_font: SafeFont = get_font(SIZES["small"])
            for i, line in enumerate(lines):
                log_surf: pygame.Surface = log_font.render(line[:40], True, COLORS["text_dim"])
                self._surface.blit(log_surf, (10, 30 + i * 14))

        ctx: pygame.Rect = pygame.Rect(0, 0, 320, 240)
        self._menu.draw(ctx)

    def handle_event(self, event: InputEvent) -> bool:
        return self._menu.handle_event(event)
