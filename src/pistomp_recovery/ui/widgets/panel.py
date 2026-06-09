from __future__ import annotations

import pygame

from pistomp_recovery.ui.colors import COLORS
from pistomp_recovery.ui.fonts import get_font
from pistomp_recovery.ui.widgets.container import Container
from pistomp_recovery.ui.widgets.misc import Box
from pistomp_recovery.ui.widgets.paint import PaintContext

TITLE_BAR_H: int = 20
CORNER_RADIUS: int = 6


class Panel(Container):
    def __init__(self, bounds: Box, title: str = "") -> None:
        super().__init__(bounds)
        self.title: str = title
        self.sel_index: int = 0

    def draw(self, ctx: PaintContext) -> None:
        surface: pygame.Surface = ctx.surface
        rect: pygame.Rect = pygame.Rect(
            self.bounds.x, self.bounds.y, self.bounds.w, self.bounds.h
        )

        pygame.draw.rect(surface, COLORS["panel_bg"], rect, border_radius=CORNER_RADIUS)
        pygame.draw.rect(
            surface, COLORS["panel_border"], rect, width=1, border_radius=CORNER_RADIUS
        )

        if self.title:
            font = get_font(20)
            title_surf: pygame.Surface = font.render(self.title, True, COLORS["text_bright"])
            title_rect: pygame.Rect = title_surf.get_rect(
                midleft=(self.bounds.x + 8, self.bounds.y + TITLE_BAR_H // 2)
            )
            surface.blit(title_surf, title_rect)

            pygame.draw.line(
                surface,
                COLORS["panel_border"],
                (self.bounds.x + 4, self.bounds.y + TITLE_BAR_H),
                (self.bounds.right - 4, self.bounds.y + TITLE_BAR_H),
            )

        content_top: int = self.bounds.y + (TITLE_BAR_H if self.title else 0)
        content_bounds: Box = Box(
            self.bounds.x, content_top, self.bounds.w, self.bounds.bottom - content_top,
        )
        content_ctx: PaintContext | None = ctx.painting(content_bounds)
        if content_ctx is not None:
            for child in self.children:
                child_ctx: PaintContext | None = content_ctx.painting(child.bounds)
                if child_ctx is not None:
                    child.draw(child_ctx)

        self._dirty_region = None
