from __future__ import annotations

from typing import Literal

Color = tuple[int, int, int] | tuple[int, int, int, int]

ColorName = Literal[
    "bg",
    "text",
    "text_dim",
    "accent",
    "warning",
    "error",
    "success",
    "title_bg",
    "title_fg",
    "sel_bg",
    "sel_fg",
    "disabled",
    "divider",
    "progress_bg",
    "progress_fg",
    "overlay",
]

# Softened EGA / QBASIC IDE palette. The classic IDE was a deep EGA blue
# (#0000AA) with bright text and a light-gray menu bar; this brightens the
# blue and warms the whites a touch so it stays legible on the small ILI9341.
# Selection is reverse video (light box, blue text) rather than a coloured
# highlight, matching DOS-era list boxes.
COLORS: dict[ColorName, Color] = {
    "bg": (26, 26, 140),         # softened EGA blue background
    "text": (240, 240, 240),     # bright body text
    "text_dim": (150, 150, 205), # de-emphasised text / separators
    "accent": (90, 230, 230),    # cyan accent (badges, values)
    "warning": (240, 210, 80),   # yellow
    "error": (240, 90, 90),      # red
    "success": (110, 230, 130),  # green
    "title_bg": (200, 200, 200), # light-gray inverted title bar
    "title_fg": (20, 20, 120),   # blue text on the title bar
    "sel_bg": (235, 235, 235),   # reverse-video reticule box
    "sel_fg": (20, 20, 120),     # blue text inside the reticule
    "disabled": (95, 95, 150),   # dimmed/non-selectable text
    "divider": (70, 70, 150),
    "progress_bg": (20, 20, 90),
    "progress_fg": (90, 230, 230),
    "overlay": (0, 0, 0, 150),
}
