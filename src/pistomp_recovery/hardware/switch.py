# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportOptionalMemberAccess=false, reportAttributeAccessIssue=false
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

NAV_SWITCH_ADC_CHAN: int = 4
THRESHOLD: int = 800
LONG_PRESS_SEC: float = 0.5


class AdcSwitch:
    def __init__(self, adc_channel: int = NAV_SWITCH_ADC_CHAN) -> None:
        self._adc_channel: int = adc_channel
        self._spi: object | None = None
        self._pressed: bool = False
        self._press_start: float = 0.0
        self._long_fired: bool = False
        self._click_pending: bool = False

    def start(self) -> None:
        try:
            import spidev  # type: ignore[import-untyped]
            self._spi = spidev.SpiDev()
            # MCP3008 ADC is on bus 0, CE1 (CE0 is the LCD). Matches pi-stomp's
            # hardware.init_spi() — reading CE0 here would talk to the display.
            self._spi.open(0, 1)
            self._spi.max_speed_hz = 1_000_000
        except ImportError:
            logger.warning("spidev not available, ADC switch disabled")
        logger.info("ADC switch started on channel %d", self._adc_channel)

    def stop(self) -> None:
        if self._spi is not None and hasattr(self._spi, "close"):
            self._spi.close()  # type: ignore[union-attr]

    def _read_adc(self) -> int:
        if self._spi is None:
            return 1023
        adc = self._spi.xfer2([1, (8 + self._adc_channel) << 4, 0])  # type: ignore[union-attr]
        return ((adc[1] & 3) << 8) + adc[2]

    def poll(self) -> int:
        value: int = self._read_adc()
        now: float = time.monotonic()

        if value <= THRESHOLD:
            if not self._pressed:
                self._pressed = True
                self._press_start = now
                self._long_fired = False
            elif not self._long_fired and now - self._press_start >= LONG_PRESS_SEC:
                self._long_fired = True
                self._pressed = False
                return -1  # long press
        else:
            if self._pressed and not self._long_fired:
                self._pressed = False
                return 1  # short click
            self._pressed = False

        return 0
