from __future__ import annotations

from typing import Callable

import pygame

from pistomp_recovery.ui.colors import COLORS, Color
from pistomp_recovery.ui.fonts import get_font
from pistomp_recovery.ui.widgets.container import Container
from pistomp_recovery.ui.widgets.misc import Box, InputEvent
from pistomp_recovery.ui.widgets.paint import PaintContext

ITEM_HEIGHT: int = 22
MARGIN: int = 4

MenuItem = tuple[str, Callable[[], None]]


class Menu(Container):
    def __init__(self, bounds: Box, title: str = "") -> None:
        super().__init__(bounds)
        self.title: str = title
        self.items: list[MenuItem] = []
        self.sel_index: int = 0
        self.scroll_offset: int = 0
        self.auto_dismiss: bool = False

    def add_item(
        self, label: str, callback: Callable[[], None]
    ) -> None:
        self.items.append((label, callback))
        self.mark_dirty()

    def clear_items(self) -> None:
        self.items.clear()
        self.sel_index = 0
        self.scroll_offset = 0
        self.mark_dirty()

    @property
    def visible_count(self) -> int:
        content_h: int = self.bounds.h - 20 if self.title else self.bounds.h
        return max(1, content_h // ITEM_HEIGHT)

    def handle_event(self, event: InputEvent) -> bool:
        if not self.items:
            return False

        if event == InputEvent.LEFT:
            self.sel_index = (self.sel_index - 1) % len(self.items)
            self._scroll_into_view()
            self.mark_dirty()
            return True
        elif event == InputEvent.RIGHT:
            self.sel_index = (self.sel_index + 1) % len(self.items)
            self._scroll_into_view()
            self.mark_dirty()
            return True
        elif event == InputEvent.CLICK:
            if 0 <= self.sel_index < len(self.items):
                _, callback = self.items[self.sel_index]
                callback()
                return True
        return False

    def _scroll_into_view(self) -> None:
        if self.sel_index < self.scroll_offset:
            self.scroll_offset = self.sel_index
        elif self.sel_index >= self.scroll_offset + self.visible_count:
            self.scroll_offset = self.sel_index - self.visible_count + 1

    def draw(self, ctx: PaintContext) -> None:
        surface: pygame.Surface = ctx.surface
        from pistomp_recovery.ui.widgets.panel import TITLE_BAR_H

        y_start: int = self.bounds.y + (TITLE_BAR_H if self.title else 0)
        x_start: int = self.bounds.x + MARGIN
        font = get_font(20)

        end: int = min(self.scroll_offset + self.visible_count, len(self.items))
        for i in range(self.scroll_offset, end):
            y: int = y_start + (i - self.scroll_offset) * ITEM_HEIGHT
            label: str = self.items[i][0]
            is_selected: bool = i == self.sel_index

            if is_selected:
                sel_rect: pygame.Rect = pygame.Rect(
                    self.bounds.x + 2, y, self.bounds.w - 4, ITEM_HEIGHT
                )
                pygame.draw.rect(surface, COLORS["selection_bg"], sel_rect, border_radius=3)

            text_color: Color = (
                COLORS["text_bright"] if is_selected else COLORS["text_dim"]
            )
            text_surf: pygame.Surface = font.render(label, True, text_color)
            text_rect: pygame.Rect = text_surf.get_rect(
                midleft=(x_start, y + ITEM_HEIGHT // 2)
            )
            surface.blit(text_surf, text_rect)

        if len(self.items) > self.visible_count:
            total: int = len(self.items)
            vis: int = self.visible_count
            bar_h: int = max(8, int(y_start + vis * ITEM_HEIGHT * vis / total))
            max_offset: int = max(1, total - vis)
            bar_y: int = y_start + int(
                (vis * ITEM_HEIGHT - bar_h) * self.scroll_offset / max_offset
            )
            scroll_rect: pygame.Rect = pygame.Rect(self.bounds.right - 4, bar_y, 2, bar_h)
            pygame.draw.rect(surface, COLORS["scroll_thumb"], scroll_rect)

        self._dirty_region = None
