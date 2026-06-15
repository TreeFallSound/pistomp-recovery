from __future__ import annotations

import pygame

from pistomp_recovery.ui.colors import COLORS
from pistomp_recovery.ui.fonts import TEXT_DY, SafeFont, get_font
from pistomp_recovery.ui.widgets.misc import Box


class ProgressBar:
    """Square, retro progress bar with an optional centred label."""

    def __init__(
        self, bounds: Box, progress: float = 0.0, label: str = ""
    ) -> None:
        self.bounds: Box = bounds
        self.progress: float = progress
        self.label: str = label

    def set_progress(self, progress: float, label: str = "") -> None:
        self.progress = max(0.0, min(1.0, progress))
        if label:
            self.label = label

    def draw(self, surface: pygame.Surface) -> None:
        rect: pygame.Rect = pygame.Rect(
            self.bounds.x, self.bounds.y, self.bounds.w, self.bounds.h
        )
        surface.fill(COLORS["progress_bg"], rect)
        pygame.draw.rect(surface, COLORS["text_dim"], rect, width=1)

        if self.progress > 0:
            fill_w: int = max(1, int(self.bounds.w * self.progress))
            fill_rect: pygame.Rect = pygame.Rect(
                self.bounds.x, self.bounds.y, fill_w, self.bounds.h
            )
            surface.fill(COLORS["progress_fg"], fill_rect)

        if self.label:
            font: SafeFont = get_font()
            label_surf: pygame.Surface = font.render(
                self.label, True, COLORS["text"]
            )
            label_rect: pygame.Rect = label_surf.get_rect(center=rect.center)
            label_rect.y += TEXT_DY
            surface.blit(label_surf, label_rect)


class StatusLine:
    """Single line of text, used for hints and progress messages."""

    def __init__(
        self, bounds: Box, text: str = "",
        color: tuple[int, int, int] | tuple[int, int, int, int] | None = None
    ) -> None:
        self.bounds: Box = bounds
        self.text: str = text
        self.color: tuple[int, int, int] | tuple[int, int, int, int] = color or COLORS["text_dim"]

    def set_text(
        self, text: str, color: tuple[int, int, int] | tuple[int, int, int, int] | None = None
    ) -> None:
        self.text = text
        if color is not None:
            self.color = color

    def draw(self, surface: pygame.Surface) -> None:
        if not self.text:
            return
        font: SafeFont = get_font()
        text_surf: pygame.Surface = font.render(self.text, True, self.color)
        text_rect: pygame.Rect = text_surf.get_rect(
            midleft=(self.bounds.x + 4, self.bounds.y + self.bounds.h // 2 + TEXT_DY)
        )
        surface.blit(text_surf, text_rect)
