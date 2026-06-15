# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false
"""Font wrapper using pygame._freetype with the bundled Mx437 IBM VGA pixel font.

The recovery UI uses a single fixed-cell bitmap font (8x16) to get the classic
QBASIC / DOS look and to fit as many characters on the 320x240 LCD as possible.
Rendering is non-antialiased so glyphs stay pixel-crisp, and the bundled TTF
ensures deterministic, pixel-identical output across dev, CI, and the Pi.

There is only one weight and one size: emphasis is done with reverse video
(see ``ui/colors.py``), not bold or larger type.
"""

from __future__ import annotations

import os

import pygame
import pygame._freetype as _freetype  # type: ignore[attr-defined]

from pistomp_recovery.pygame_init import init as _pg_init

_FONT_DIR: str = os.path.dirname(__file__)
_FONT_PATH: str = os.path.join(_FONT_DIR, "Mx437_IBM_VGA_8x16.ttf")

#: Native pixel size of the bundled font. Every glyph cell is FONT_SIZE tall.
FONT_SIZE: int = 16

#: Vertical nudge (px) applied when blitting text into a lane, so glyphs sit
#: optically centred rather than flush with the top of their cell.
TEXT_DY: int = 1

#: Retained so legacy call sites keep type-checking; every entry snaps to the
#: single native pixel size (the theme no longer varies font size).
SIZES: dict[str, int] = {
    "title": FONT_SIZE,
    "heading": FONT_SIZE,
    "body": FONT_SIZE,
    "small": FONT_SIZE,
    "status": FONT_SIZE,
}


class SafeFont:
    """Drop-in replacement for pygame.font.Font that uses pygame._freetype.

    Always renders without antialiasing so the pixel font stays crisp.
    """

    def __init__(self, path: str | None, size: int) -> None:
        _pg_init()
        self._ft: _freetype.Font = _freetype.Font(path, size)  # type: ignore[assignment]
        self._ft.antialiased = False  # type: ignore[union-attr]
        self._ft.pad = True  # type: ignore[union-attr]

    def render(
        self, text: str, antialias: bool, color: tuple[int, int, int] | tuple[int, int, int, int]
    ) -> pygame.Surface:
        result = self._ft.render(text, color)  # type: ignore[union-attr]
        return result[0]

    def get_rect(self, text: str) -> pygame.Rect:
        return self._ft.get_rect(text)  # type: ignore[union-attr]

    def size(self, text: str) -> tuple[int, int]:
        rect = self.get_rect(text)
        return (rect.width, rect.height)

    @property
    def height(self) -> int:
        return self._ft.get_rect("Ag").height  # type: ignore[union-attr]


FONT_CACHE: dict[int, SafeFont] = {}

_cell_cache: tuple[int, int] | None = None


def get_font(size: int = FONT_SIZE, bold: bool | None = None) -> SafeFont:
    """Return the single bundled pixel font.

    ``size`` and ``bold`` are accepted for source compatibility with the old
    multi-size/bold API but ignored: the theme uses one fixed-cell font.
    """
    del size, bold
    if FONT_SIZE not in FONT_CACHE:
        FONT_CACHE[FONT_SIZE] = SafeFont(_FONT_PATH, FONT_SIZE)
    return FONT_CACHE[FONT_SIZE]


def cell_size() -> tuple[int, int]:
    """Return the (width, height) of one monospace character cell, in pixels."""
    global _cell_cache
    if _cell_cache is None:
        font: SafeFont = get_font()
        advance: int = font.get_rect("MM").width - font.get_rect("M").width
        _cell_cache = (advance, FONT_SIZE)
    return _cell_cache


def text_width(text: str) -> int:
    """Pixel width of ``text`` in the monospace cell grid."""
    return cell_size()[0] * len(text)
