from __future__ import annotations

import logging

import pygame

from pistomp_recovery.constants import LCD_HEIGHT, LCD_WIDTH
from pistomp_recovery.hardware.lcd import LcdSpi
from pistomp_recovery.pygame_init import init as pg_init

logger = logging.getLogger(__name__)


class Display:
    def __init__(self, lcd: LcdSpi) -> None:
        self._lcd: LcdSpi = lcd
        self.width: int = LCD_WIDTH
        self.height: int = LCD_HEIGHT
        self._surface: pygame.Surface | None = None

    def init(self) -> None:
        pg_init()
        self._surface = pygame.Surface((self.width, self.height))
        self._surface.fill((0, 0, 0))
        self._lcd.init()
        self.update(self._surface)

    def update(self, surface: pygame.Surface) -> None:
        self._lcd.update(surface)

    @property
    def surface(self) -> pygame.Surface:
        assert self._surface is not None, "Display not initialized"
        return self._surface
