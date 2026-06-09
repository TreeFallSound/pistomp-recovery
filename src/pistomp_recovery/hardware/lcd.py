# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from pistomp_recovery.constants import INIT_STAMP, LCD_HEIGHT, LCD_WIDTH

if TYPE_CHECKING:
    import pygame

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
            import board  # type: ignore[import-untyped]
            import digitalio  # type: ignore[import-untyped]
            from adafruit_rgb_display import ili9341  # type: ignore[import-untyped]
        except ImportError:
            logger.error("LCD dependencies not available (board, adafruit_rgb_display)")
            raise

        spi = board.SPI()  # type: ignore[union-attr]
        cs_pin = digitalio.DigitalInOut(board.CE0)  # type: ignore[union-attr]
        dc_pin = digitalio.DigitalInOut(board.D6)  # type: ignore[union-attr]
        rst_pin = digitalio.DigitalInOut(board.D5)  # type: ignore[union-attr]

        rst = None if self.has_system_splash else rst_pin  # type: ignore[assignment]

        self._disp = ili9341.ILI9341(  # type: ignore[union-attr]
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

    def update(self, surface: pygame.Surface) -> None:
        import pygame

        with self._lock:
            if self._disp is None:
                return

            img: pygame.Surface = pygame.transform.rotate(
                surface, 180 if self._flip else 0
            )
            rgb: bytes = pygame.image.tostring(img, "RGB")

            from PIL import Image  # type: ignore[import-untyped]

            pil_img: Image.Image = Image.frombytes("RGB", (LCD_WIDTH, LCD_HEIGHT), rgb)
            self._disp.image(pil_img)  # type: ignore[union-attr]

    def clear(self) -> None:
        if self._disp is not None:
            from PIL import Image  # type: ignore[import-untyped]

            black: Image.Image = Image.new("RGB", (LCD_WIDTH, LCD_HEIGHT), (0, 0, 0))
            self._disp.image(black)  # type: ignore[union-attr]
