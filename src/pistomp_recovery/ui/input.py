from __future__ import annotations

import logging
import time

from pistomp_recovery.hardware.encoder import EncoderInput
from pistomp_recovery.ui.widgets.misc import InputEvent

logger = logging.getLogger(__name__)

SWITCH_GPIO: int = 16
LONG_PRESS_SEC: float = 0.5


class InputManager:
    def __init__(self, encoder: EncoderInput) -> None:
        self._encoder: EncoderInput = encoder
        self._running: bool = False
        self._switch_pressed_at: float | None = None
        self._long_fired: bool = False
        self._switch: object | None = None

    def start(self) -> None:
        try:
            from gpiozero import Button  # type: ignore[import-untyped]
            self._switch = Button(SWITCH_GPIO, bounce_time=0.02)
            switch = self._switch
            assert isinstance(switch, Button)
            switch.when_pressed = self._on_press
            switch.when_released = self._on_release
        except ImportError:
            logger.warning("gpiozero not available, switch input disabled")

        self._running = True

    def stop(self) -> None:
        self._running = False
        if self._switch is not None and hasattr(self._switch, 'close'):
            self._switch.close()  # type: ignore[union-attr]

    def _on_press(self) -> None:
        self._switch_pressed_at = time.monotonic()
        self._long_fired = False

    def _on_release(self) -> None:
        if self._switch_pressed_at is not None and not self._long_fired:
            self._switch_pressed_at = None

    def poll(self) -> list[InputEvent]:
        events: list[InputEvent] = []

        direction: int = self._encoder.poll()
        if direction > 0:
            events.append(InputEvent.RIGHT)
        elif direction < 0:
            events.append(InputEvent.LEFT)

        if self._switch_pressed_at is not None:
            elapsed: float = time.monotonic() - self._switch_pressed_at
            if not self._long_fired and elapsed >= LONG_PRESS_SEC:
                events.append(InputEvent.LONG_CLICK)
                self._long_fired = True
                self._switch_pressed_at = None
            elif self._long_fired:
                pass
            elif self._switch is not None:
                pass

        return events
