# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportMissingImports=false, reportUnknownArgumentType=false
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

NAV_PIN_D: int = 17
NAV_PIN_CLK: int = 4

# Number of attempts (with backoff) to claim the encoder pins. When pi-stomp
# stops (Conflicts=), its process must fully release the GPIO lines before we
# can reserve them. A clean SIGTERM exit releases them promptly, but we retry to
# cover the window where the kernel hasn't reaped the old descriptor yet.
_CLAIM_ATTEMPTS: int = 20
_CLAIM_BACKOFF_SEC: float = 0.5


class EncoderInput:
    """Quadrature decoder for the nav encoder.

    Uses gpiozero.Button on both phases exactly like pi-stomp's pistomp/encoder.py
    (Button defaults to pull_up=True / active-low), driving the same gray-code
    decode/debounce state machine. We keep a poll() accumulator API rather than a
    per-detent callback so RecoveryApp can drain rotation each frame.
    """

    def __init__(self, pin_d: int = NAV_PIN_D, pin_clk: int = NAV_PIN_CLK) -> None:
        self._pin_d: int = pin_d
        self._pin_clk: int = pin_clk
        self._direction: int = 0
        self._lock: threading.Lock = threading.Lock()

        self._data: object | None = None
        self._clk: object | None = None

        self._prev_next_code: int = 0
        self._store: int = 0

        # 16 possible gray codes. 1=valid, 0=invalid (bounce).
        self._rot_enc_table: list[int] = [
            0, 1, 1, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0,
        ]

    def start(self) -> None:
        try:
            from gpiozero import Button
            from gpiozero.exc import GPIOZeroError
        except ImportError:
            logger.warning("gpiozero not available, encoder input disabled")
            return

        for attempt in range(_CLAIM_ATTEMPTS):
            try:
                self._data = Button(self._pin_d)
                self._clk = Button(self._pin_clk)
                break
            except GPIOZeroError as e:
                self._close_buttons()
                if attempt < _CLAIM_ATTEMPTS - 1:
                    logger.info(
                        "Encoder pins busy (%s), retry %d/%d",
                        str(e), attempt + 1, _CLAIM_ATTEMPTS,
                    )
                    time.sleep(_CLAIM_BACKOFF_SEC)
                    continue
                logger.exception("Failed to claim encoder pins after %d attempts", _CLAIM_ATTEMPTS)
                return

        data = self._data
        clk = self._clk
        if data is None or clk is None:
            return

        data.when_pressed = self._gpio_callback  # type: ignore[attr-defined]
        data.when_released = self._gpio_callback  # type: ignore[attr-defined]
        clk.when_pressed = self._gpio_callback  # type: ignore[attr-defined]
        clk.when_released = self._gpio_callback  # type: ignore[attr-defined]

        logger.info("Encoder input started on pins D=%d CLK=%d", self._pin_d, self._pin_clk)

    def stop(self) -> None:
        self._close_buttons()

    def _close_buttons(self) -> None:
        for btn in (self._data, self._clk):
            if btn is not None and hasattr(btn, "close"):
                try:
                    btn.close()  # type: ignore[attr-defined]
                except Exception:
                    pass
        self._data = None
        self._clk = None

    def _process_gpios(self) -> int:
        # Decode/debounce adapted from
        # https://www.best-microcontroller-projects.com/rotary-encoder.html
        # (same implementation as pi-stomp's Encoder._process_gpios).
        self._prev_next_code <<= 2
        if self._data is not None and self._data.value:  # type: ignore[attr-defined]
            self._prev_next_code |= 0x02
        if self._clk is not None and self._clk.value:  # type: ignore[attr-defined]
            self._prev_next_code |= 0x01
        self._prev_next_code &= 0x0f

        direction = 0
        if self._rot_enc_table[self._prev_next_code]:
            self._store <<= 4
            self._store |= self._prev_next_code
            if (self._store & 0xff) == 0x2b:  # full sequence 13,4,2,11 → clockwise
                direction = 1
            if (self._store & 0xff) == 0x17:  # full sequence 14,8,1,7 → counter-clockwise
                direction = -1
        if direction != 0:
            self._store = self._prev_next_code
        return direction

    def _gpio_callback(self) -> None:
        d = self._process_gpios()
        if d != 0:
            with self._lock:
                self._direction += d

    def poll(self) -> int:
        with self._lock:
            d: int = self._direction
            self._direction = 0
        return d
