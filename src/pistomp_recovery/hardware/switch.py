# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportUnknownArgumentType=false
from __future__ import annotations

import logging
import time
from typing import Protocol

logger = logging.getLogger(__name__)


class Switch(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def poll(self) -> int: ...

NAV_SWITCH_ADC_CHAN: int = 4
THRESHOLD: int = 800
LONG_PRESS_SEC: float = 0.5

# pi-Stomp Core (v2) wires the nav encoder's push switch straight to this BCM
# GPIO pin (see ../pi-stomp pistomp/pistompcore.py's `EncoderController(...,
# sw_pin=1)` -> gpioswitch.GpioSwitch(1, ...)) rather than through the MCP3008
# ADC used on v3/Tre. It is not routed through the footswitch debounce chip.
NAV_SWITCH_GPIO_PIN: int = 1


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


class GpioSwitch:
    """v2/Core nav-encoder button: a plain GPIO input, debounced via gpiozero.

    Mirrors pi-stomp's ``pistomp.gpioswitch.GpioSwitch`` semantics (press/hold/
    release polled from the main loop) but returns ints like ``AdcSwitch.poll()``
    so ``InputManager`` can treat either switch interchangeably.
    """

    _CLAIM_ATTEMPTS: int = 20
    _CLAIM_BACKOFF_SEC: float = 0.5

    def __init__(self, pin: int = NAV_SWITCH_GPIO_PIN) -> None:
        self._pin: int = pin
        self._button: object | None = None
        self._pressed: bool = False
        self._press_start: float = 0.0
        self._long_fired: bool = False

    def start(self) -> None:
        try:
            from gpiozero import Button  # pyright: ignore[reportMissingImports]
            from gpiozero.exc import GPIOZeroError  # pyright: ignore[reportMissingImports]
        except ImportError:
            logger.warning("gpiozero not available, GPIO switch disabled")
            return

        for attempt in range(self._CLAIM_ATTEMPTS):
            try:
                self._button = Button(self._pin, bounce_time=0.008)
                break
            except GPIOZeroError as e:
                self._button = None
                if attempt < self._CLAIM_ATTEMPTS - 1:
                    logger.info(
                        "Switch pin busy (%s), retry %d/%d",
                        str(e), attempt + 1, self._CLAIM_ATTEMPTS,
                    )
                    time.sleep(self._CLAIM_BACKOFF_SEC)
                    continue
                logger.exception(
                    "Failed to claim switch pin %d after %d attempts",
                    self._pin, self._CLAIM_ATTEMPTS,
                )
                return

        logger.info("GPIO switch started on pin %d", self._pin)

    def stop(self) -> None:
        if self._button is not None and hasattr(self._button, "close"):
            self._button.close()  # type: ignore[union-attr]
        self._button = None

    def poll(self) -> int:
        if self._button is None:
            return 0
        is_pressed: bool = self._button.is_pressed  # type: ignore[union-attr]
        now: float = time.monotonic()

        if is_pressed:
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
