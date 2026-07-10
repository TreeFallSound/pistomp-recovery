from __future__ import annotations

from pathlib import Path

from pistomp_recovery.constants import CONFIG_DIR


def is_v2() -> bool:
    """True if the device is pi-Stomp Core (v2, Pi 3/4) rather than Tre (v3, Pi 5).

    Reads the hardware version from the same config file pi-stomp uses
    (written by firstboot.sh -> modify_version.sh). Shared by the LCD (panel
    orientation/reset) and input (nav-switch wiring) backends.
    """
    try:
        import yaml

        with open(Path(CONFIG_DIR) / "default_config.yml") as f:
            cfg = yaml.safe_load(f)
        version = float(cfg.get("hardware", {}).get("version", 3.0))
        return version < 3.0
    except Exception:
        return False
