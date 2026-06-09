from __future__ import annotations

INIT_STAMP: str = "/run/lcd.init"
PISTOMP_USER: str = "pistomp"
PISTOMP_HOME: str = "/home/pistomp"
DATA_DIR: str = f"{PISTOMP_HOME}/data"
CONFIG_DIR: str = f"{DATA_DIR}/config"
PEDALBOARDS_DIR: str = f"{DATA_DIR}/.pedalboards"
RECOVERY_DIR: str = f"{PISTOMP_HOME}/.pistomp-recovery"
PACKAGES_STAMP_FILE: str = f"{RECOVERY_DIR}/packages.stamp"
FACTORY_PACKAGES_FILE: str = "/etc/pistomp/factory-packages.list"
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

PACKAGE_SERVICES: dict[str, list[str]] = {
    "jack2-pistomp": ["jack", "mod-host", "mod-ui", "mod-ala-pi-stomp"],
    "mod-host-pistomp": ["mod-host", "mod-ui", "mod-ala-pi-stomp"],
    "mod-ui": ["mod-ui"],
    "pi-stomp": ["mod-ala-pi-stomp"],
    "pistomp-recovery": [],
    "mod-midi-merger": ["mod-host"],
    "mod-ttymidi": ["mod-host"],
    "amidithru": ["jack"],
    "fluidsynth-headless": ["jack"],
    "libfluidsynth2-compat": [],
    "lg": [],
    "lcd-splash": [],
    "sfizz-pistomp": ["jack"],
    "jack_capture": ["jack"],
    "hylia": ["jack"],
}


def services_for_packages(packages: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    chain: list[str] = list(PISTOMP_SERVICES)
    for pkg in packages:
        svcs: list[str] = PACKAGE_SERVICES.get(pkg, chain)
        for svc in svcs:
            if svc not in seen:
                seen.add(svc)
                result.append(svc)
    ordered: list[str] = [svc for svc in chain if svc in seen]
    return ordered
