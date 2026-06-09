"""Emulator LCD — renders into a pygame Surface for interactive development.

No SPI, no GPIO, no real hardware. Used by the emulator window
and also serves as a test-friendly display backend.
"""

from __future__ import annotations

import pygame

from pistomp_recovery.constants import LCD_WIDTH, LCD_HEIGHT


class LcdPygame:
    """LCD implementation that renders into a pygame Surface.

    In the emulator this is the primary display. In tests, the FakeLcd
    in conftest.py is preferred since it captures PIL Images for snapshot
    comparison.
    """

    def __init__(
        self,
        width: int = LCD_WIDTH,
        height: int = LCD_HEIGHT,
    ) -> None:
        self.width: int = width
        self.height: int = height
        self.surface: pygame.Surface = pygame.Surface((width, height))
        self._has_splash: bool = False
        pygame.font.init()

    @property
    def has_system_splash(self) -> bool:
        return self._has_splash

    def init(self) -> None:
        self._has_splash = True
        self.surface.fill((0, 0, 0))

    def update(self, surface: pygame.Surface) -> None:
        self.surface.blit(surface, (0, 0))

    def clear(self) -> None:
        self.surface.fill((0, 0, 0))