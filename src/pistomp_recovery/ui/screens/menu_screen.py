from __future__ import annotations

from typing import Callable

import pygame

from pistomp_recovery.constants import LCD_HEIGHT, LCD_WIDTH
from pistomp_recovery.items import Row, Target
from pistomp_recovery.ui.colors import COLORS
from pistomp_recovery.ui.fonts import TEXT_DY, cell_size, get_font, text_width
from pistomp_recovery.ui.screens import Screen
from pistomp_recovery.ui.widgets.confirm_dialog import ConfirmDialog
from pistomp_recovery.ui.widgets.header import Header
from pistomp_recovery.ui.widgets.misc import Box, InputEvent
from pistomp_recovery.ui.widgets.text import ProgressBar, StatusLine

SEP: str = " | "

# Navigation position: (row index, target index). The header icon is (-1, 0).
NavPos = tuple[int, int]
HEADER: NavPos = (-1, 0)


class MenuScreen(Screen):
    """Universal screen: a header bar plus a list of :class:`Row` reticules.

    Encoder rotation walks every enabled :class:`Target` in reading order
    (header icon first, then rows top-to-bottom, left-to-right); click
    activates the selected target. Destructive targets pop a confirm modal.
    Long-press is intentionally inert — back/exit is the header icon only.
    """

    def __init__(
        self,
        surface: pygame.Surface,
        title: str,
        rows: list[Row],
        header_icon: Target,
        *,
        mode: str = "",
        domain: str = "",
        reload_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(surface)
        self._title: str = title
        self._rows: list[Row] = rows
        self._header_target: Target = header_icon
        self._header: Header = Header(title, header_icon.label)
        self._state: str = "LIST"
        self._confirm_dialog: ConfirmDialog | None = None
        self._scroll: int = 0
        self._status_text: str = ""
        self._progress_title: str = ""
        self._progress_done: bool = False
        self._mode: str = mode
        self._domain: str = domain
        self._reload_callback: Callable[[], None] | None = reload_callback
        cw, ch = cell_size()
        self._progress_bar: ProgressBar = ProgressBar(
            Box(cw * 2, LCD_HEIGHT // 2, LCD_WIDTH - cw * 4, ch)
        )
        self._status: StatusLine = StatusLine(
            Box(0, LCD_HEIGHT - ch, LCD_WIDTH, ch)
        )
        self._nav: list[NavPos] = []
        self._sel: int = 0
        self._build_nav()

        # TAIL state fields.
        self._tail_lines: list[str] = []
        self._tail_scroll: int = 0
        self._tail_cancel: Callable[[], None] | None = None
        self._tail_on_header: bool = True
        self._saved_header_target: Target | None = None
        self._saved_header_icon: str = ""

    # -- structure ----------------------------------------------------------

    def set_rows(self, rows: list[Row]) -> None:
        self._rows = rows
        self._scroll = 0
        if self._state == "LIST":
            self._build_nav()

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def domain(self) -> str:
        return self._domain

    def reload(self) -> None:
        """Re-run the caller's reload callback to refresh this screen's rows."""
        if self._reload_callback is not None:
            self._reload_callback()

    def _build_nav(self) -> None:
        nav: list[NavPos] = [HEADER]
        for r, row in enumerate(self._rows):
            for ti, target in enumerate(row.targets):
                if target.enabled:
                    nav.append((r, ti))
        self._nav = nav
        # Prefer the first real target; fall back to the header icon.
        self._sel = 1 if len(nav) > 1 else 0
        self._scroll_into_view()

    def _target_at(self, pos: NavPos) -> Target:
        if pos == HEADER:
            return self._header_target
        return self._rows[pos[0]].targets[pos[1]]

    # -- progress -----------------------------------------------------------

    def set_progress(
        self, title: str, progress: float, status: str, done: bool = False
    ) -> None:
        self._state = "PROGRESS"
        self._progress_title = title
        self._progress_bar.set_progress(progress)
        self._status_text = status
        self._progress_done = done

    def clear_progress(self) -> None:
        self._state = "LIST"
        self._progress_done = False
        self._status_text = ""
        self._build_nav()

    def set_status(self, text: str) -> None:
        self._status_text = text

    # -- tail (streaming output) --------------------------------------------

    def set_tail(self, title: str, cancel_callback: Callable[[], None]) -> None:
        self._saved_header_target = self._header_target
        self._saved_header_icon = self._header.icon
        self._header_target = Target("Cancel", cancel_callback)
        self._header.icon = "Cancel"
        self._header.title = title
        self._state = "TAIL"
        self._tail_lines = []
        self._tail_scroll = 0
        self._tail_cancel = cancel_callback
        self._tail_on_header = True

    def append_tail(self, line: str) -> None:
        self._tail_lines.append(line)
        lines: int = self._content_lines()
        self._tail_scroll = max(0, len(self._tail_lines) - lines)

    def clear_tail(self) -> None:
        if self._saved_header_target is not None:
            self._header_target = self._saved_header_target
            self._header.icon = self._saved_header_icon
            self._saved_header_target = None
            self._saved_header_icon = ""
        self._state = "LIST"
        self._tail_lines = []
        self._tail_cancel = None
        self._build_nav()

    # -- geometry -----------------------------------------------------------

    def _content_top(self) -> int:
        # Header height plus a top gap equal to the left text margin (one cell),
        # so the first row sits the same distance from the title bar as text
        # sits from the left edge.
        cw, ch = cell_size()
        return ch + cw

    def _content_lines(self) -> int:
        ch: int = cell_size()[1]
        return max(1, (LCD_HEIGHT - self._content_top() - ch) // ch)

    def _scroll_into_view(self) -> None:
        r: int = self._nav[self._sel][0]
        if r < 0:
            return
        lines: int = self._content_lines()
        if r < self._scroll:
            self._scroll = r
        elif r >= self._scroll + lines:
            self._scroll = r - lines + 1

    # -- input --------------------------------------------------------------

    def handle_event(self, event: InputEvent) -> list[Box]:
        if self._state == "TAIL":
            return self._handle_tail_event(event)
        if self._state == "PROGRESS":
            if self._progress_done and event == InputEvent.CLICK:
                self.reload()
                self.clear_progress()
            return [Box(0, 0, LCD_WIDTH, LCD_HEIGHT)]
        if self._state == "CONFIRM":
            if self._confirm_dialog is not None:
                self._confirm_dialog.handle_event(event)
            return [Box(0, 0, LCD_WIDTH, LCD_HEIGHT)]
        if event == InputEvent.LEFT:
            old_rect = self._selection_rect()
            old_scroll = self._scroll
            self._sel = (self._sel - 1) % len(self._nav)
            self._scroll_into_view()
            if self._scroll != old_scroll:
                return [self._content_rect()]
            new_rect = self._selection_rect()
            return [old_rect, new_rect]
        if event == InputEvent.RIGHT:
            old_rect = self._selection_rect()
            old_scroll = self._scroll
            self._sel = (self._sel + 1) % len(self._nav)
            self._scroll_into_view()
            if self._scroll != old_scroll:
                return [self._content_rect()]
            new_rect = self._selection_rect()
            return [old_rect, new_rect]
        if event == InputEvent.CLICK:
            self._activate()
            return [Box(0, 0, LCD_WIDTH, LCD_HEIGHT)]
        return []

    def _handle_tail_event(self, event: InputEvent) -> list[Box]:
        if event == InputEvent.LEFT:
            if self._tail_on_header:
                self._tail_on_header = False
                self._tail_scroll = max(0, len(self._tail_lines) - 1)
            elif self._tail_scroll > 0:
                self._tail_scroll -= 1
            else:
                self._tail_on_header = True
            return [Box(0, 0, LCD_WIDTH, LCD_HEIGHT)]
        if event == InputEvent.RIGHT:
            if self._tail_on_header:
                self._tail_on_header = False
                self._tail_scroll = 0
            else:
                lines: int = self._content_lines()
                max_scroll: int = max(0, len(self._tail_lines) - lines)
                if self._tail_scroll < max_scroll:
                    self._tail_scroll += 1
                else:
                    self._tail_on_header = True
            return [Box(0, 0, LCD_WIDTH, LCD_HEIGHT)]
        if event == InputEvent.CLICK and self._tail_on_header:
            if self._tail_cancel is not None:
                self._tail_cancel()
            return [Box(0, 0, LCD_WIDTH, LCD_HEIGHT)]
        return []

    def _selection_rect(self) -> Box:
        """Bounding rect of the current selection (for dirty tracking)."""
        pos: NavPos = self._nav[self._sel]
        ch: int = cell_size()[1]
        if pos == HEADER:
            return Box(0, 0, LCD_WIDTH, ch)
        content_y0: int = self._content_top()
        r: int = pos[0]
        y: int = content_y0 + (r - self._scroll) * ch
        if y >= LCD_HEIGHT or y + ch <= 0:
            return Box(0, 0, 0, 0)
        y = max(0, y)
        return Box(0, y, LCD_WIDTH, ch)

    def _content_rect(self) -> Box:
        """Bounding rect of the scrollable content area."""
        ch: int = cell_size()[1]
        return Box(0, self._content_top(), LCD_WIDTH, self._content_lines() * ch)

    def _activate(self) -> None:
        target: Target = self._target_at(self._nav[self._sel])
        if target.confirm is not None:
            self._open_confirm(target, target.confirm)
        else:
            target.on_select()

    def _open_confirm(self, target: Target, text: str) -> None:
        self._state = "CONFIRM"
        self._confirm_dialog = ConfirmDialog(
            self._surface,
            text,
            lambda: self._do_confirm(target),
            self._cancel_confirm,
        )

    def _do_confirm(self, target: Target) -> None:
        self._state = "LIST"
        self._confirm_dialog = None
        target.on_select()

    def _cancel_confirm(self) -> None:
        self._state = "LIST"
        self._confirm_dialog = None

    # -- drawing ------------------------------------------------------------

    def draw(self, clip: Box | None = None) -> None:
        if clip is None:
            clip = Box(0, 0, LCD_WIDTH, LCD_HEIGHT)
        # Scope all drawing to the dirty region so a partial redraw only
        # touches the pixels that actually changed.
        self._surface.set_clip(clip.to_pygame_rect())
        try:
            self._surface.fill(COLORS["bg"])

            if self._state == "TAIL":
                self._draw_tail()
                return

            if self._state == "PROGRESS":
                self._draw_progress()
                return

            self._header.draw(self._surface, icon_selected=self._sel == 0)
            self._draw_rows()
            if self._status_text:
                self._status.set_text(self._status_text)
                self._status.draw(self._surface)

            if self._state == "CONFIRM" and self._confirm_dialog is not None:
                self._confirm_dialog.draw()
        finally:
            self._surface.set_clip(None)

    def _draw_progress(self) -> None:
        ch: int = cell_size()[1]
        font = get_font()
        title_surf: pygame.Surface = font.render(
            self._progress_title, True, COLORS["text"]
        )
        self._surface.blit(
            title_surf, (LCD_WIDTH // 2 - title_surf.get_width() // 2, ch * 3 + TEXT_DY)
        )
        self._progress_bar.draw(self._surface)
        if self._status_text:
            self._status.set_text(self._status_text)
            self._status.draw(self._surface)

    def _draw_tail(self) -> None:
        self._header.draw(self._surface, icon_selected=self._tail_on_header)
        self._draw_tail_lines()

    def _draw_tail_lines(self) -> None:
        cw, ch = cell_size()
        content_y0: int = self._content_top()
        lines: int = self._content_lines()
        end: int = min(self._tail_scroll + lines, len(self._tail_lines))
        font = get_font()

        for i in range(self._tail_scroll, end):
            y: int = content_y0 + (i - self._tail_scroll) * ch
            line: str = self._tail_lines[i]
            selected: bool = i == self._tail_scroll and not self._tail_on_header

            if selected:
                self._surface.fill(
                    COLORS["sel_bg"],
                    pygame.Rect(0, y, LCD_WIDTH, ch),
                )
                color = COLORS["sel_fg"]
            else:
                color = COLORS["text"]

            x: int = cw
            surf = font.render(line, True, color)
            self._surface.blit(surf, (x, y + TEXT_DY))

        self._draw_tail_scrollbar(lines, content_y0)

    def _draw_tail_scrollbar(self, lines: int, content_y0: int) -> None:
        total: int = len(self._tail_lines)
        if total <= lines:
            return
        ch: int = cell_size()[1]
        track_h: int = lines * ch
        bar_h: int = max(ch, track_h * lines // total)
        max_off: int = max(1, total - lines)
        bar_y: int = content_y0 + (track_h - bar_h) * self._tail_scroll // max_off
        self._surface.fill(
            COLORS["text_dim"], pygame.Rect(LCD_WIDTH - 2, bar_y, 2, bar_h)
        )

    def _draw_rows(self) -> None:
        cw, ch = cell_size()
        content_y0: int = self._content_top()
        lines: int = self._content_lines()
        end: int = min(self._scroll + lines, len(self._rows))
        sel_pos: NavPos = self._nav[self._sel]

        for r in range(self._scroll, end):
            row: Row = self._rows[r]
            y: int = content_y0 + (r - self._scroll) * ch
            x: int = cw

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

        self._draw_scrollbar(lines, content_y0)

    def _draw_target(self, target: Target, x: int, y: int, selected: bool) -> int:
        ch: int = cell_size()[1]
        w: int = text_width(target.label)
        if selected:
            self._surface.fill(
                COLORS["sel_bg"], pygame.Rect(x - 1, y, w + 2, ch)
            )
            color = COLORS["sel_fg"]
        else:
            color = COLORS["text"] if target.enabled else COLORS["disabled"]
        surf: pygame.Surface = get_font().render(target.label, True, color)
        self._surface.blit(surf, (x, y + TEXT_DY))
        return x + w

    def _draw_scrollbar(self, lines: int, content_y0: int) -> None:
        total: int = len(self._rows)
        if total <= lines:
            return
        ch: int = cell_size()[1]
        track_h: int = lines * ch
        bar_h: int = max(ch, track_h * lines // total)
        max_off: int = max(1, total - lines)
        bar_y: int = content_y0 + (track_h - bar_h) * self._scroll // max_off
        self._surface.fill(
            COLORS["text_dim"], pygame.Rect(LCD_WIDTH - 2, bar_y, 2, bar_h)
        )
