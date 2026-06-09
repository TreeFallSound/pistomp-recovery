from __future__ import annotations

import pygame

from pistomp_recovery.ui.widgets.misc import Box


class PaintContext:
    __slots__ = ("surface", "clip", "frame")

    def __init__(self, surface: pygame.Surface, clip: Box, frame: Box) -> None:
        self.surface: pygame.Surface = surface
        self.clip: Box = clip
        self.frame: Box = frame

    def painting(self, child_frame: Box) -> "PaintContext | None":
        child_clip: Box | None = self.clip.clip(child_frame.offset(self.frame.x, self.frame.y))
        if child_clip is None:
            return None
        return PaintContext(self.surface, child_clip, child_frame)

    def set_clip(self) -> None:
        pygame_rect: pygame.Rect = pygame.Rect(
            self.clip.x, self.clip.y, self.clip.w, self.clip.h
        )
        self.surface.set_clip(pygame_rect)

    def clear_clip(self) -> None:
        self.surface.set_clip(None)
