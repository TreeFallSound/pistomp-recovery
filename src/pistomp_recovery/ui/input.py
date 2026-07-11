from __future__ import annotations

import logging

from pistomp_recovery.hardware.encoder import EncoderInput
from pistomp_recovery.hardware.switch import Switch
from pistomp_recovery.hardware.tweak_pot import TweakInput
from pistomp_recovery.ui.widgets.misc import InputEvent

logger = logging.getLogger(__name__)


class InputManager:
    def __init__(
        self,
        encoder: EncoderInput,
        switch: Switch,
        tweaks: list[TweakInput],
    ) -> None:
        self._encoder: EncoderInput = encoder
        self._switch: Switch = switch
        self._tweaks: list[TweakInput] = tweaks

    def start(self) -> None:
        self._encoder.start()
        self._switch.start()
        for tweak in self._tweaks:
            tweak.start()

    def stop(self) -> None:
        self._encoder.stop()
        self._switch.stop()
        for tweak in self._tweaks:
            tweak.stop()

    def poll(self) -> list[InputEvent]:
        events: list[InputEvent] = []

        direction: int = self._encoder.poll()
        if direction > 0:
            events.append(InputEvent.RIGHT)
        elif direction < 0:
            events.append(InputEvent.LEFT)

        tweak_dir: int = 0
        for tweak in self._tweaks:
            tweak_dir = tweak.poll()
            if tweak_dir != 0:
                break
        if tweak_dir > 0:
            events.append(InputEvent.TWEAK1_RIGHT)
        elif tweak_dir < 0:
            events.append(InputEvent.TWEAK1_LEFT)

        if len(self._tweaks) > 1:
            tweak2_dir: int = self._tweaks[1].poll()
            if tweak2_dir > 0:
                events.append(InputEvent.TWEAK2_RIGHT)
            elif tweak2_dir < 0:
                events.append(InputEvent.TWEAK2_LEFT)

        sw: int = self._switch.poll()
        if sw == 1:
            events.append(InputEvent.CLICK)
        elif sw == -1:
            events.append(InputEvent.LONG_CLICK)

        return events
