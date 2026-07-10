# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportUnknownArgumentType=false
from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)

ADC_MAX: int = 1023

# Discrete positions across the pot's full sweep. Position maps directly to a
# step index (like a scrollbar), so this is also how many LEFT/RIGHT events
# a full end-to-end sweep produces.
NUM_STEPS: int = 40


class TweakInput(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def poll(self) -> int: ...


class TweakPot:
    """
    v2 Tweak knob: a fixed-sweep potentiometer via the MCP3008 ADC.
    Core's tweak knobs have hard end-stops and no detents.
    Leftmost = step 0, rightmost = step NUM_STEPS-1
    Emits a LEFT/RIGHT event for each delta step.
    """

    def __init__(self, adc_channel: int) -> None:
        self._adc_channel: int = adc_channel
        self._spi: object | None = None
        self._last_step: int | None = None

    def start(self) -> None:
        try:
            import spidev  # type: ignore[import-untyped]

            self._spi = spidev.SpiDev()
            # MCP3008 ADC is on bus 0, CE1 (CE0 is the LCD). Matches AdcSwitch;
            # a second independent open of the same spidev char device is fine
            # for a human-rate-limited control (no shared-bus contention risk).
            self._spi.open(0, 1)
            self._spi.max_speed_hz = 1_000_000
        except ImportError:
            logger.warning(
                "spidev not available, tweak pot on channel %d disabled", self._adc_channel
            )
        logger.info("Tweak pot started on ADC channel %d", self._adc_channel)

    def stop(self) -> None:
        if self._spi is not None and hasattr(self._spi, "close"):
            self._spi.close()  # type: ignore[union-attr]

    def _read_adc(self) -> int:
        if self._spi is None:
            return 0
        adc = self._spi.xfer2([1, (8 + self._adc_channel) << 4, 0])  # type: ignore[union-attr]
        return ((adc[1] & 3) << 8) + adc[2]

    def _current_step(self) -> int:
        value: int = self._read_adc()
        return min(NUM_STEPS - 1, value * NUM_STEPS // (ADC_MAX + 1))

    def poll(self) -> int:
        step: int = self._current_step()

        if self._last_step is None:
            # First read: adopt wherever the knob already sits rather than
            # scrolling to catch up to it on startup.
            self._last_step = step
            return 0

        if step == self._last_step:
            return 0

        direction: int = 1 if step > self._last_step else -1
        self._last_step += direction
        return direction
