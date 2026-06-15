from __future__ import annotations

from typing import Callable

import pygame

from pistomp_recovery.constants import LCD_HEIGHT, LCD_WIDTH
from pistomp_recovery.ui.colors import COLORS, ColorName
from pistomp_recovery.ui.fonts import TEXT_DY, cell_size, get_font, text_width
from pistomp_recovery.ui.widgets.misc import InputEvent

DIALOG_W: int = 256
DIALOG_H: int = 96


class ConfirmDialog:
    """Modal overlay with No/Yes choices, rendered in the QBASIC style.

    A double-line box over a dimmed page; the focused choice is drawn in
    reverse video. Intercepts all input until dismissed. Encoder rotates
    between No and Yes; click activates.
    """

    def __init__(
        self,
        surface: pygame.Surface,
        title: str,
        on_confirm: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        self._surface: pygame.Surface = surface
        self._title: str = title
        self._on_confirm: Callable[[], None] = on_confirm
        self._on_cancel: Callable[[], None] = on_cancel
        self._confirmed: bool = False

    def handle_event(self, event: InputEvent) -> bool:
        if event in (InputEvent.LEFT, InputEvent.RIGHT):
            self._confirmed = not self._confirmed
            return True
        if event == InputEvent.CLICK:
            if self._confirmed:
                self._on_confirm()
            else:
                self._on_cancel()
            return True
        return False

    def draw(self) -> None:
        overlay: pygame.Surface = pygame.Surface(
            (LCD_WIDTH, LCD_HEIGHT), pygame.SRCALPHA
        )
        overlay.fill(COLORS["overlay"])
        self._surface.blit(overlay, (0, 0))

        ch: int = cell_size()[1]
        x: int = (LCD_WIDTH - DIALOG_W) // 2
        y: int = (LCD_HEIGHT - DIALOG_H) // 2
        rect: pygame.Rect = pygame.Rect(x, y, DIALOG_W, DIALOG_H)
        self._surface.fill(COLORS["bg"], rect)
        pygame.draw.rect(self._surface, COLORS["text"], rect, width=1)
        pygame.draw.rect(
            self._surface, COLORS["text"],
            pygame.Rect(x + 2, y + 2, DIALOG_W - 4, DIALOG_H - 4), width=1,
        )

        font = get_font()
        line_y: int = y + ch
        for line in self._title.split("\n"):
            surf: pygame.Surface = font.render(line, True, COLORS["text"])
            self._surface.blit(
                surf, (LCD_WIDTH // 2 - surf.get_width() // 2, line_y + TEXT_DY)
            )
            line_y += ch

        btn_y: int = y + DIALOG_H - ch * 2
        self._draw_button("No", x + DIALOG_W // 4, btn_y, not self._confirmed)
        self._draw_button("Yes", x + DIALOG_W * 3 // 4, btn_y, self._confirmed)

    def _draw_button(self, label: str, cx: int, y: int, selected: bool) -> None:
        cw, ch = cell_size()
        font = get_font()
        w: int = text_width(label)
        x: int = cx - w // 2
        fg: ColorName = "sel_fg" if selected else "text"
        if selected:
            box: pygame.Rect = pygame.Rect(x - cw, y, w + cw * 2, ch)
            self._surface.fill(COLORS["sel_bg"], box)
        surf: pygame.Surface = font.render(label, True, COLORS[fg])
        self._surface.blit(surf, (x, y + TEXT_DY))
