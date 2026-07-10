from __future__ import annotations

import logging

from pistomp_recovery.hardware.encoder import EncoderInput
from pistomp_recovery.hardware.switch import Switch
from pistomp_recovery.ui.widgets.misc import InputEvent

logger = logging.getLogger(__name__)


class InputManager:
    def __init__(
        self,
        encoder: EncoderInput,
        switch: Switch,
        tweak1: EncoderInput,
    ) -> None:
        self._encoder: EncoderInput = encoder
        self._switch: Switch = switch
        self._tweak1: EncoderInput = tweak1

    def start(self) -> None:
        self._encoder.start()
        self._switch.start()
        self._tweak1.start()

    def stop(self) -> None:
        self._encoder.stop()
        self._switch.stop()
        self._tweak1.stop()

    def poll(self) -> list[InputEvent]:
        events: list[InputEvent] = []

        direction: int = self._encoder.poll()
        if direction > 0:
            events.append(InputEvent.RIGHT)
        elif direction < 0:
            events.append(InputEvent.LEFT)

        tweak_dir: int = self._tweak1.poll()
        if tweak_dir > 0:
            events.append(InputEvent.TWEAK1_RIGHT)
        elif tweak_dir < 0:
            events.append(InputEvent.TWEAK1_LEFT)

        sw: int = self._switch.poll()
        if sw == 1:
            events.append(InputEvent.CLICK)
        elif sw == -1:
            events.append(InputEvent.LONG_CLICK)

        return events
