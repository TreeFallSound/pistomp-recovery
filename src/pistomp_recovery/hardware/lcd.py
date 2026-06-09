# pyright: basic
from __future__ import annotations

import logging
import threading
from pathlib import Path

from pistomp_recovery.constants import INIT_STAMP, LCD_HEIGHT, LCD_WIDTH

logger = logging.getLogger(__name__)


class LcdSpi:
    def __init__(self, baudrate: int = 24_000_000, flip: bool = True) -> None:
        self._baudrate: int = baudrate
        self._flip: bool = flip
        self._disp: object | None = None
        self._lock: threading.Lock = threading.Lock()

    @property
    def width(self) -> int:
        return LCD_WIDTH

    @property
    def height(self) -> int:
        return LCD_HEIGHT

    @property
    def has_system_splash(self) -> bool:
        return Path(INIT_STAMP).exists()

    def init(self) -> None:
        try:
            import board  # pyright: ignore[reportMissingImports]
            import digitalio  # pyright: ignore[reportMissingImports]
            from adafruit_rgb_display import ili9341  # pyright: ignore[reportMissingImports]
        except ImportError:
            logger.error("LCD dependencies not available (board, adafruit_rgb_display)")
            raise

        spi = board.SPI()
        cs_pin = digitalio.DigitalInOut(board.CE0)
        dc_pin = digitalio.DigitalInOut(board.D6)
        rst_pin = digitalio.DigitalInOut(board.D5)

        rst: object | None = None if self.has_system_splash else rst_pin

        self._disp = ili9341.ILI9341(
            spi,
            cs=cs_pin,
            dc=dc_pin,
            rst=rst,
            baudrate=self._baudrate,
        )

        if not self.has_system_splash:
            self._create_stamp()

        logger.info("LCD initialized: %dx%d", LCD_WIDTH, LCD_HEIGHT)

    def _create_stamp(self) -> None:
        try:
            Path(INIT_STAMP).touch()
        except OSError:
            pass

    def update(self, surface: object) -> None:
        import pygame

        with self._lock:
            if self._disp is None:
                return

            assert isinstance(surface, pygame.Surface)
            img: pygame.Surface = pygame.transform.rotate(surface, 180 if self._flip else 0)
            rgb: bytes = pygame.image.tostring(img, "RGB")

            from PIL import Image  # type: ignore[import-untyped]

            pil_img: Image.Image = Image.frombytes("RGB", (LCD_WIDTH, LCD_HEIGHT), rgb)
            self._disp.image(pil_img)  # type: ignore[union-attr]

    def clear(self) -> None:
        if self._disp is not None:
            from PIL import Image  # type: ignore[import-untyped]

            black: Image.Image = Image.new("RGB", (LCD_WIDTH, LCD_HEIGHT), (0, 0, 0))
            self._disp.image(black)  # type: ignore[union-attr]
