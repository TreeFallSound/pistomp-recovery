from __future__ import annotations

from typing import Callable

import pygame

from pistomp_recovery.constants import LCD_HEIGHT, LCD_WIDTH
from pistomp_recovery.items import Row, Target
from pistomp_recovery.service import CrashInfo, is_crash_result
from pistomp_recovery.ui.colors import COLORS
from pistomp_recovery.ui.fonts import TEXT_DY, cell_size, get_font, text_width
from pistomp_recovery.ui.screens.menu_screen import HEADER, SEP, MenuScreen
from pistomp_recovery.ui.widgets.header import ICON_EXIT
from pistomp_recovery.ui.widgets.misc import Box, InputEvent

_HSCROLL_STEP: int = 40
_TEXTAREA_LINES: int = 6


class CrashScreen(MenuScreen):
    """Crash recovery: failed-service summary, log textarea, and actions.

    The log textarea shows the last 4 log lines. Tweak1 scrolls them
    horizontally. Clicking opens a fullscreen log view.
    """

    def __init__(
        self,
        surface: pygame.Surface,
        on_resume: Callable[[], None],
        on_recovery: Callable[[], None],
        on_show_log: Callable[[], None],
        crash_info: CrashInfo | None = None,
    ) -> None:
        self._hscroll: int = 0
        self._log_lines: list[str] = []
        self._on_show_log: Callable[[], None] = on_show_log

        rows: list[Row] = []
        if crash_info is not None:
            for svc, state in crash_info.service_states.items():
                result: str = crash_info.service_results.get(svc, "")
                crashed: bool = state == "failed" or is_crash_result(result)
                is_failed: bool = crash_info.failed_service == svc
                marker: str = "  <--" if is_failed else ""
                label: str = "crashed" if crashed else state
                rows.append(Row(prefix=f"{svc}: {label}{marker}"))

            if crash_info.crash_log:
                self._log_lines = crash_info.crash_log.strip().split("\n")[-_TEXTAREA_LINES:]
                rows.append(Row(prefix="---", separator=True))
                rows.append(Row((Target("", on_show_log),)))
                rows.append(Row(prefix="---", separator=True))
            else:
                rows.append(Row(prefix=""))

        rows.append(
            Row((
                Target("RESUME", on_resume),
                Target("RECOVERY", on_recovery),
            ))
        )

        super().__init__(
            surface,
            title="pi-Stomp! Crash",
            rows=rows,
            header_icon=Target(ICON_EXIT, on_resume),
        )

    def _textarea_row_index(self) -> int | None:
        if not self._log_lines:
            return None
        for i, row in enumerate(self._rows):
            if row.targets and not row.targets[0].label:
                return i
        return None

    def _row_visual_height(self, row_index: int) -> int:
        ch: int = cell_size()[1]
        if self._textarea_row_index() == row_index:
            return ch * _TEXTAREA_LINES
        return ch

    def _total_visual_height(self) -> int:
        total = 0
        for i in range(len(self._rows)):
            total += self._row_visual_height(i)
        return total

    def _content_lines(self) -> int:
        ch: int = cell_size()[1]
        return max(1, (LCD_HEIGHT - self._content_top()) // ch)

    def _scroll_into_view(self) -> None:
        r: int = self._nav[self._sel][0]
        if r < 0:
            return
        ch: int = cell_size()[1]
        content_h: int = (LCD_HEIGHT - self._content_top())
        # Compute visual offset of row r
        offset = 0
        for i in range(r):
            offset += self._row_visual_height(i)
        if offset < self._scroll * ch:
            self._scroll = offset // ch
        elif offset + self._row_visual_height(r) > self._scroll * ch + content_h:
            self._scroll = (offset + self._row_visual_height(r) - content_h + ch - 1) // ch

    def handle_event(self, event: InputEvent) -> list[Box]:
        if self._state != "LIST":
            return super().handle_event(event)

        textarea_idx = self._textarea_row_index()
        if textarea_idx is None:
            return super().handle_event(event)

        sel_pos = self._nav[self._sel]
        on_textarea = sel_pos != HEADER and sel_pos[0] == textarea_idx

        if on_textarea and event in (InputEvent.TWEAK1_LEFT, InputEvent.TWEAK1_RIGHT):
            max_w = max(text_width(line) for line in self._log_lines) if self._log_lines else 0
            view_w = LCD_WIDTH - cell_size()[0] * 2
            if event == InputEvent.TWEAK1_RIGHT:
                self._hscroll = max(0, self._hscroll - _HSCROLL_STEP)
            else:
                self._hscroll = min(max(0, max_w - view_w), self._hscroll + _HSCROLL_STEP)
            return [Box(0, 0, LCD_WIDTH, LCD_HEIGHT)]

        if on_textarea and event == InputEvent.CLICK:
            self._on_show_log()
            return [Box(0, 0, LCD_WIDTH, LCD_HEIGHT)]

        return super().handle_event(event)

    def _selection_rect(self) -> Box:
        pos = self._nav[self._sel]
        ch: int = cell_size()[1]
        if pos == HEADER:
            return Box(0, 0, LCD_WIDTH, ch)
        r: int = pos[0]
        y = self._row_visual_y(r)
        h = self._row_visual_height(r)
        if y >= LCD_HEIGHT or y + h <= 0:
            return Box(0, 0, 0, 0)
        return Box(0, max(0, y), LCD_WIDTH, h)

    def _row_visual_y(self, row_index: int) -> int:
        content_y0: int = self._content_top()
        ch: int = cell_size()[1]
        offset = 0
        for i in range(row_index):
            offset += self._row_visual_height(i)
        return content_y0 + offset - self._scroll * ch

    def _draw_rows(self) -> None:
        cw, _ch = cell_size()
        content_y0: int = self._content_top()
        content_h: int = LCD_HEIGHT - content_y0
        sel_pos = self._nav[self._sel]
        textarea_idx = self._textarea_row_index()

        for r in range(len(self._rows)):
            row: Row = self._rows[r]
            y = self._row_visual_y(r)
            rh = self._row_visual_height(r)

            if y + rh <= 0 or y >= LCD_HEIGHT:
                continue

            x: int = cw

            if r == textarea_idx and self._log_lines:
                self._draw_textarea(y, sel_pos == (r, 0))
                continue

            if row.prefix:
                prefix_color = COLORS["disabled"] if row.separator else COLORS["text"]
                surf: pygame.Surface = get_font().render(
                    row.prefix, True, prefix_color
                )
                self._surface.blit(surf, (x, y + TEXT_DY))
                x += text_width(row.prefix)

            for ti, target in enumerate(row.targets):
                if ti > 0:
                    sep_surf: pygame.Surface = get_font().render(
                        SEP, True, COLORS["text_dim"]
                    )
                    self._surface.blit(sep_surf, (x, y + TEXT_DY))
                    x += text_width(SEP)
                x = self._draw_target(target, x, y, selected=sel_pos == (r, ti))

            if row.right:
                rw: int = text_width(row.right)
                right_surf: pygame.Surface = get_font().render(
                    row.right, True, COLORS["accent"]
                )
                self._surface.blit(right_surf, (LCD_WIDTH - rw - cw, y + TEXT_DY))

        self._draw_scrollbar(content_h, content_y0)

    def _draw_textarea(self, y: int, selected: bool) -> None:
        cw, ch = cell_size()
        font = get_font()
        x = cw - self._hscroll

        if selected:
            rect = pygame.Rect(0, y, LCD_WIDTH, ch * _TEXTAREA_LINES)
            pygame.draw.rect(self._surface, (255, 255, 0), rect, width=1)

        for i, line in enumerate(self._log_lines):
            line_y = y + i * ch
            surf = font.render(line, True, COLORS["text"])
            self._surface.blit(surf, (x, line_y + TEXT_DY))

    def _draw_scrollbar(self, lines: int, content_y0: int) -> None:
        total_h: int = self._total_visual_height()
        if total_h <= lines:
            return
        ch: int = cell_size()[1]
        bar_h: int = max(ch, lines * lines // total_h)
        max_off: int = max(1, total_h - lines)
        bar_y: int = content_y0 + (lines - bar_h) * (self._scroll * ch) // max_off
        self._surface.fill(
            COLORS["text_dim"], pygame.Rect(LCD_WIDTH - 2, bar_y, 2, bar_h)
        )
