from __future__ import annotations

from typing import Literal

Color = tuple[int, int, int] | tuple[int, int, int, int]

ColorName = Literal[
    "bg",
    "panel_bg",
    "panel_border",
    "selection_bg",
    "text_bright",
    "text_dim",
    "text_accent",
    "text_warning",
    "text_error",
    "text_success",
    "progress_bg",
    "progress_fg",
    "scroll_thumb",
    "divider",
    "overlay",
]

COLORS: dict[ColorName, Color] = {
    "bg": (18, 18, 24),
    "panel_bg": (28, 28, 38),
    "panel_border": (60, 60, 78),
    "selection_bg": (50, 90, 160),
    "text_bright": (240, 240, 240),
    "text_dim": (140, 140, 160),
    "text_accent": (80, 180, 255),
    "text_warning": (255, 180, 40),
    "text_error": (255, 80, 80),
    "text_success": (80, 220, 120),
    "progress_bg": (40, 40, 55),
    "progress_fg": (70, 140, 220),
    "scroll_thumb": (80, 80, 100),
    "divider": (50, 50, 68),
    "overlay": (0, 0, 0, 160),
}
