from __future__ import annotations

from typing import Callable

import pygame

from pistomp_recovery.constants import LCD_HEIGHT, LCD_WIDTH
from pistomp_recovery.ui.colors import COLORS
from pistomp_recovery.ui.fonts import TEXT_DY, cell_size, get_font, text_width
from pistomp_recovery.ui.screens import Screen
from pistomp_recovery.ui.widgets.header import Header, ICON_BACK
from pistomp_recovery.ui.widgets.misc import Box, InputEvent

_HSCROLL_STEP: int = 40


class LogViewScreen(Screen):
    """Fullscreen log viewer with vertical and horizontal scrolling.

    Nav encoder selects lines. Tweak1 scrolls all lines horizontally.
    LONG_CLICK or navigating to and clicking the back icon exits.
    """

    def __init__(
        self,
        surface: pygame.Surface,
        lines: list[str],
        on_back: Callable[[], None],
    ) -> None:
        super().__init__(surface)
        self._lines: list[str] = lines
        self._on_back: Callable[[], None] = on_back
        self._header: Header = Header("Crash Log", ICON_BACK)
        self._scroll: int = max(0, len(lines) - self._content_lines())
        self._hscroll: int = 0
        self._sel: int = len(lines) - 1 if lines else 0
        self._on_header: bool = False

    def draw(self, clip: Box | None = None) -> None:
        if clip is None:
            clip = Box(0, 0, LCD_WIDTH, LCD_HEIGHT)
        self._surface.set_clip(clip.to_pygame_rect())
        try:
            self._surface.fill(COLORS["bg"])
            self._header.draw(self._surface, icon_selected=self._on_header)
            self._draw_lines()
            self._draw_scrollbar()
        finally:
            self._surface.set_clip(None)

    def _content_top(self) -> int:
        cw, ch = cell_size()
        return ch + cw

    def _content_lines(self) -> int:
        ch: int = cell_size()[1]
        return max(1, (LCD_HEIGHT - self._content_top()) // ch)

    def _draw_lines(self) -> None:
        cw, ch = cell_size()
        content_y0: int = self._content_top()
        lines: int = self._content_lines()
        end: int = min(self._scroll + lines, len(self._lines))
        font = get_font()

        for i in range(self._scroll, end):
            y: int = content_y0 + (i - self._scroll) * ch
            line: str = self._lines[i]
            selected: bool = i == self._sel and not self._on_header

            if selected:
                self._surface.fill(
                    COLORS["sel_bg"],
                    pygame.Rect(0, y, LCD_WIDTH, ch),
                )
                color = COLORS["sel_fg"]
            else:
                color = COLORS["text"]

            x: int = cw - self._hscroll
            surf = font.render(line, True, color)
            self._surface.blit(surf, (x, y + TEXT_DY))

    def _draw_scrollbar(self) -> None:
        lines: int = self._content_lines()
        total: int = len(self._lines)
        if total <= lines:
            return
        ch: int = cell_size()[1]
        content_y0: int = self._content_top()
        track_h: int = lines * ch
        bar_h: int = max(ch, track_h * lines // total)
        max_off: int = max(1, total - lines)
        bar_y: int = content_y0 + (track_h - bar_h) * self._scroll // max_off
        self._surface.fill(
            COLORS["text_dim"], pygame.Rect(LCD_WIDTH - 2, bar_y, 2, bar_h)
        )

    def handle_event(self, event: InputEvent) -> list[Box]:
        if event == InputEvent.LEFT:
            if self._on_header:
                self._on_header = False
                self._sel = len(self._lines) - 1
            elif self._sel == 0:
                self._on_header = True
            else:
                self._sel -= 1
            self._scroll_into_view()
            return [Box(0, 0, LCD_WIDTH, LCD_HEIGHT)]
        if event == InputEvent.RIGHT:
            if self._on_header:
                self._on_header = False
                self._sel = 0
            elif self._sel >= len(self._lines) - 1:
                self._on_header = True
            else:
                self._sel += 1
            self._scroll_into_view()
            return [Box(0, 0, LCD_WIDTH, LCD_HEIGHT)]
        if event == InputEvent.TWEAK1_LEFT:
            self._hscroll = max(0, self._hscroll - _HSCROLL_STEP)
            return [Box(0, 0, LCD_WIDTH, LCD_HEIGHT)]
        if event == InputEvent.TWEAK1_RIGHT:
            max_w = max(text_width(l) for l in self._lines) if self._lines else 0
            view_w = LCD_WIDTH - cell_size()[0] * 2
            self._hscroll = min(max(0, max_w - view_w), self._hscroll + _HSCROLL_STEP)
            return [Box(0, 0, LCD_WIDTH, LCD_HEIGHT)]
        if event == InputEvent.CLICK and self._on_header:
            self._on_back()
            return [Box(0, 0, LCD_WIDTH, LCD_HEIGHT)]
        if event == InputEvent.LONG_CLICK:
            self._on_back()
            return [Box(0, 0, LCD_WIDTH, LCD_HEIGHT)]
        return []

    def _scroll_into_view(self) -> None:
        if self._on_header:
            return
        lines: int = self._content_lines()
        if self._sel < self._scroll:
            self._scroll = self._sel
        elif self._sel >= self._scroll + lines:
            self._scroll = self._sel - lines + 1
