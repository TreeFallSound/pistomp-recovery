# pyright: reportUnknownMemberType=false
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

NAV_PIN_D: int = 17
NAV_PIN_CLK: int = 4
ENCODER_DEBOUNCE_MS: int = 5


class EncoderInput:
    def __init__(self, pin_d: int = NAV_PIN_D, pin_clk: int = NAV_PIN_CLK) -> None:
        self._pin_d: int = pin_d
        self._pin_clk: int = pin_clk
        self._direction: int = 0
        self._lock: threading.Lock = threading.Lock()
        self._running: bool = False
        self._button_d: object | None = None
        self._button_clk: object | None = None

    def start(self) -> None:
        try:
            from gpiozero import Button  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("gpiozero not available, encoder input disabled")
            return

        self._button_d = Button(self._pin_d, bounce_time=ENCODER_DEBOUNCE_MS / 1000)  # type: ignore[assignment]
        self._button_clk = Button(self._pin_clk, bounce_time=ENCODER_DEBOUNCE_MS / 1000)  # type: ignore[assignment]

        edge_handler = self._on_edge
        assert self._button_d is not None
        assert self._button_clk is not None
        self._button_d.when_pressed = edge_handler  # type: ignore[union-attr]
        self._button_d.when_released = edge_handler  # type: ignore[union-attr]
        self._button_clk.when_pressed = edge_handler  # type: ignore[union-attr]
        self._button_clk.when_released = edge_handler  # type: ignore[union-attr]

        self._running = True
        logger.info("Encoder input started on pins D=%d CLK=%d", self._pin_d, self._pin_clk)

    def stop(self) -> None:
        self._running = False
        for btn in (self._button_d, self._button_clk):
            if btn is not None and hasattr(btn, "close"):
                btn.close()  # type: ignore[union-attr]

    def _on_edge(self, pin: object) -> None:
        if not self._running:
            return
        if self._button_d is None or self._button_clk is None:
            return

        d_val: bool = bool(self._button_d.is_pressed)  # type: ignore[union-attr]
        clk_val: bool = bool(self._button_clk.is_pressed)  # type: ignore[union-attr]

        with self._lock:
            self._direction += 1 if clk_val != d_val else -1

    def poll(self) -> int:
        with self._lock:
            net: int = self._direction
            self._direction = 0
            return net // 2 if abs(net) >= 2 else 0
