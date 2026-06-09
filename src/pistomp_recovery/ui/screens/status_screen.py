from __future__ import annotations

import pygame

from pistomp_recovery.packages.manager import UpdateState
from pistomp_recovery.ui.colors import COLORS
from pistomp_recovery.ui.fonts import SIZES, SafeFont, get_font
from pistomp_recovery.ui.widgets.misc import Box, InputEvent
from pistomp_recovery.ui.widgets.text import ProgressBar, StatusLine


class StatusScreen:
    def __init__(self, surface: pygame.Surface) -> None:
        self._surface: pygame.Surface = surface
        self._progress: ProgressBar = ProgressBar(Box(20, 80, 280, 30))
        self._status: StatusLine = StatusLine(Box(20, 120, 280, 22))
        self._title_text: str = "Working..."
        self._cancel_requested: bool = False

    def update_from_manager(self, state: UpdateState, progress: float, text: str) -> None:
        self._progress.set_progress(progress)
        self._status.set_text(text)

        state_titles: dict[UpdateState, str] = {
            UpdateState.DOWNLOADING: "Downloading...",
            UpdateState.INSTALLING: "Installing...",
            UpdateState.HEALTH_CHECKING: "Verifying...",
            UpdateState.STAMPING: "Saving snapshot...",
            UpdateState.ROLLING_BACK: "Rolling back...",
            UpdateState.DONE: "Complete",
            UpdateState.FAILED: "Failed",
            UpdateState.IDLE: "Ready",
        }
        self._title_text = state_titles.get(state, "Working...")

    def draw(self) -> None:
        self._surface.fill(COLORS["bg"])

        title_font: SafeFont = get_font(SIZES["title"])
        title_surf: pygame.Surface = title_font.render(
            self._title_text, True, COLORS["text_bright"]
        )
        title_rect: pygame.Rect = title_surf.get_rect(centerx=160, y=30)
        self._surface.blit(title_surf, title_rect)

        ctx: pygame.Rect = pygame.Rect(0, 0, 320, 240)
        self._progress.draw(ctx)
        self._status.draw(ctx)

    def handle_event(self, event: InputEvent) -> bool:
        if event == InputEvent.LONG_CLICK:
            self._cancel_requested = True
            return True
        return False
