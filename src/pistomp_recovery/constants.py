from __future__ import annotations

INIT_STAMP: str = "/run/lcd.init"
PISTOMP_USER: str = "pistomp"
PISTOMP_HOME: str = "/home/pistomp"
DATA_DIR: str = f"{PISTOMP_HOME}/data"
CONFIG_DIR: str = f"{DATA_DIR}/config"
PEDALBOARDS_DIR: str = f"{DATA_DIR}/.pedalboards"
RECOVERY_DIR: str = f"{PISTOMP_HOME}/.pistomp-recovery"
LCD_WIDTH: int = 320
LCD_HEIGHT: int = 240

FACTORY_BRANCH: str = "factory"
DEVICE_BRANCH: str = "device"

FACET_NAMES: tuple[str, ...] = ("config", "pedalboards", "packages", "system")

PISTOMP_PACKAGES: tuple[str, ...] = (
    "jack2-pistomp",
    "mod-host-pistomp",
    "mod-midi-merger",
    "mod-ttymidi",
    "amidithru",
    "fluidsynth-headless",
    "libfluidsynth2-compat",
    "lg",
    "lcd-splash",
    "sfizz-pistomp",
    "jack_capture",
    "hylia",
    "pi-stomp",
    "mod-ui",
    "pistomp-recovery",
)

PISTOMP_SERVICES: tuple[str, ...] = (
    "jack",
    "mod-host",
    "mod-ui",
    "mod-ala-pi-stomp",
    "mod-amidithru",
    "browsepy",
)
