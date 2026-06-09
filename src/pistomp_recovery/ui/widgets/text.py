from __future__ import annotations

import pygame

from pistomp_recovery.ui.colors import COLORS, Color
from pistomp_recovery.ui.fonts import SafeFont, get_font
from pistomp_recovery.ui.widgets.misc import Box
from pistomp_recovery.ui.widgets.paint import PaintContext
from pistomp_recovery.ui.widgets.widget import Widget


class TextWidget(Widget):
    def __init__(
        self,
        bounds: Box,
        text: str,
        color: Color | None = None,
        font_size: int = 20,
    ) -> None:
        super().__init__(bounds)
        self.text: str = text
        self.color: Color = color or COLORS["text_bright"]
        self.font_size: int = font_size
        self._font: SafeFont | None = None

    def draw(self, ctx: PaintContext) -> None:
        if self._font is None:
            self._font = get_font(self.font_size)
        text_surf: pygame.Surface = self._font.render(self.text, True, self.color)
        text_rect: pygame.Rect = text_surf.get_rect(
            midleft=(self.bounds.x, self.bounds.y + self.bounds.h // 2)
        )
        ctx.surface.blit(text_surf, text_rect)
        self._dirty = False


class ProgressBar(Widget):
    def __init__(
        self, bounds: Box, progress: float = 0.0, label: str = ""
    ) -> None:
        super().__init__(bounds)
        self.progress: float = progress
        self.label: str = label

    def set_progress(self, progress: float, label: str = "") -> None:
        self.progress = max(0.0, min(1.0, progress))
        if label:
            self.label = label
        self.mark_dirty()

    def draw(self, ctx: PaintContext) -> None:
        surface: pygame.Surface = ctx.surface
        rect: pygame.Rect = pygame.Rect(
            self.bounds.x, self.bounds.y, self.bounds.w, self.bounds.h
        )

        pygame.draw.rect(surface, COLORS["progress_bg"], rect, border_radius=3)

        if self.progress > 0:
            fill_w: int = max(1, int(self.bounds.w * self.progress))
            fill_rect: pygame.Rect = pygame.Rect(
                self.bounds.x, self.bounds.y, fill_w, self.bounds.h
            )
            pygame.draw.rect(surface, COLORS["progress_fg"], fill_rect, border_radius=3)

        if self.label:
            font: SafeFont = get_font(18)
            label_surf: pygame.Surface = font.render(
                self.label, True, COLORS["text_bright"]
            )
            label_rect: pygame.Rect = label_surf.get_rect(center=rect.center)
            surface.blit(label_surf, label_rect)

        self._dirty = False


class StatusLine(Widget):
    def __init__(
        self, bounds: Box, text: str = "", color: Color | None = None
    ) -> None:
        super().__init__(bounds)
        self.text: str = text
        self.color: Color = color or COLORS["text_dim"]

    def set_text(
        self, text: str, color: Color | None = None
    ) -> None:
        self.text = text
        if color is not None:
            self.color = color
        self.mark_dirty()

    def draw(self, ctx: PaintContext) -> None:
        if not self.text:
            return
        font: SafeFont = get_font(18)
        text_surf: pygame.Surface = font.render(self.text, True, self.color)
        text_rect: pygame.Rect = text_surf.get_rect(
            midleft=(self.bounds.x + 4, self.bounds.y + self.bounds.h // 2)
        )
        ctx.surface.blit(text_surf, text_rect)
        self._dirty = False
