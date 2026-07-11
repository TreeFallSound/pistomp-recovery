# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from pistomp_recovery.constants import CONFIG_DIR

logger = logging.getLogger(__name__)


def is_v2() -> bool:
    """True if the device is pi-Stomp Core (v2, Pi 3/4) rather than Tre (v3, Pi 5).

    Reads the hardware version from the same config file pi-stomp uses
    (written by firstboot.sh -> modify_version.sh). Shared by the LCD (panel
    orientation/reset) and input (nav-switch wiring) backends.
    """
    try:
        with open(Path(CONFIG_DIR) / "default_config.yml") as f:
            cfg = yaml.safe_load(f)
        version = float(cfg.get("hardware", {}).get("version", 3.0))
        return version < 3.0
    except Exception:
        return False


def tweak_adc_channels() -> list[int]:
    """ADC channels for Core's Tweak knob(s), read from the live default_config.yml."""
    try:
        with open(Path(CONFIG_DIR) / "default_config.yml") as f:
            cfg = yaml.safe_load(f)
        controllers = cfg.get("hardware", {}).get("analog_controllers") or []
        channels: list[int] = []
        for controller in controllers:
            if controller.get("type", "KNOB") != "KNOB":
                continue
            adc_input = controller.get("adc_input")
            if adc_input is not None:
                channels.append(int(adc_input))
        return channels
    except Exception:
        logger.exception("Failed to read tweak ADC channels from default_config.yml")
        return []
