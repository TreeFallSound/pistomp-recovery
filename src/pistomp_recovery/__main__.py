from __future__ import annotations

import argparse
import logging
import signal
import subprocess
import time

from pistomp_recovery.facets.base import Facet
from pistomp_recovery.facets.config_facet import ConfigFacet
from pistomp_recovery.facets.packages_facet import PackagesFacet
from pistomp_recovery.facets.pedalboards_facet import PedalboardsFacet
from pistomp_recovery.facets.system_facet import SystemFacet
from pistomp_recovery.hardware.encoder import EncoderInput
from pistomp_recovery.hardware.lcd import LcdSpi
from pistomp_recovery.packages.manager import PackageManager
from pistomp_recovery.service import (
    BootMode,
    get_boot_mode,
    get_crash_log,
    start_main_app,
    stop_main_app,
)
from pistomp_recovery.ui.display import Display
from pistomp_recovery.ui.input import InputManager
from pistomp_recovery.ui.screens.config_screen import ConfigScreen
from pistomp_recovery.ui.screens.crash import CrashScreen
from pistomp_recovery.ui.screens.main_menu import MainMenuScreen, MenuAction
from pistomp_recovery.ui.screens.system_info import SystemInfoScreen
from pistomp_recovery.ui.screens.updates import UpdatesScreen
from pistomp_recovery.ui.widgets.misc import InputEvent

logger = logging.getLogger(__name__)

POLL_INTERVAL: float = 0.03


class RecoveryApp:
    def __init__(self, boot_mode: BootMode) -> None:
        self._boot_mode: BootMode = boot_mode
        self._running: bool = True
        self._lcd: LcdSpi = LcdSpi()
        self._encoder: EncoderInput = EncoderInput()
        self._input: InputManager = InputManager(self._encoder)
        self._display: Display = Display(self._lcd)
        self._pkg_manager: PackageManager = PackageManager()
        self._facets: dict[str, Facet] = {
            "config": ConfigFacet(),
            "pedalboards": PedalboardsFacet(),
            "packages": PackagesFacet(),
            "system": SystemFacet(),
        }
        self._current_screen: str = "crash" if boot_mode == BootMode.CRASH_RECOVERY else "menu"

    def init(self) -> None:
        stop_main_app()
        self._display.init()
        self._encoder.start()
        self._input.start()
        logger.info("Recovery app initialized (boot mode: %s)", self._boot_mode.name)

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        while self._running:
            events: list[InputEvent] = self._input.poll()
            for event in events:
                self._handle_event(event)
            self._draw_current_screen()
            time.sleep(POLL_INTERVAL)

    def _handle_event(self, event: InputEvent) -> None:
        if self._current_screen == "crash":
            self._make_crash_screen()
            if event in (InputEvent.CLICK, InputEvent.LONG_CLICK):
                self._current_screen = "menu"

        elif self._current_screen == "menu":
            menu_screen: MainMenuScreen = self._make_menu_screen()
            if menu_screen.handle_event(event):
                menu_action: MenuAction | None = menu_screen.action
                if menu_action is not None:
                    self._on_menu_action(menu_action)

        elif self._current_screen == "updates":
            updates_screen: UpdatesScreen = self._make_updates_screen()
            if not updates_screen.handle_event(event):
                self._current_screen = "menu"

        elif self._current_screen == "config":
            config_screen: ConfigScreen = self._make_config_screen()
            if not config_screen.handle_event(event):
                self._current_screen = "menu"

        elif self._current_screen == "system_info":
            info_screen: SystemInfoScreen = self._make_system_info_screen()
            if not info_screen.handle_event(event):
                self._current_screen = "menu"

    def _on_menu_action(self, action: MenuAction) -> None:
        if action == MenuAction.RESUME:
            self._resume_main_app()
        elif action == MenuAction.SYSTEM_INFO:
            self._current_screen = "system_info"
        elif action == MenuAction.PACKAGE_UPDATES:
            self._current_screen = "updates"
        elif action == MenuAction.CONFIG_MANAGEMENT:
            self._current_screen = "config"
        elif action == MenuAction.FACTORY_RESET:
            pass
        elif action == MenuAction.REBOOT:
            subprocess.run(["systemctl", "reboot"], check=False)
        elif action == MenuAction.POWER_OFF:
            subprocess.run(["systemctl", "poweroff"], check=False)

    def _resume_main_app(self) -> None:
        logger.info("Resuming main app")
        start_main_app()
        self._running = False

    def _make_crash_screen(self) -> CrashScreen:
        return CrashScreen(
            self._display.surface,
            crash_log=get_crash_log(),
            on_resume=self._resume_main_app,
            on_recovery=lambda: setattr(self, '_current_screen', 'menu'),
        )

    def _make_menu_screen(self) -> MainMenuScreen:
        return MainMenuScreen(self._display.surface)

    def _make_updates_screen(self) -> UpdatesScreen:
        screen: UpdatesScreen = UpdatesScreen(self._display.surface, self._pkg_manager)
        screen.check_updates()
        return screen

    def _make_config_screen(self) -> ConfigScreen:
        return ConfigScreen(self._display.surface)

    def _make_system_info_screen(self) -> SystemInfoScreen:
        screen: SystemInfoScreen = SystemInfoScreen(self._display.surface)
        screen.refresh()
        return screen

    def _draw_current_screen(self) -> None:
        if self._current_screen == "menu":
            screen: MainMenuScreen = self._make_menu_screen()
            screen.draw()
        self._display.update(self._display.surface)

    def cleanup(self) -> None:
        self._encoder.stop()
        self._input.stop()
        logger.info("Recovery app cleaned up")


def main(args: list[str] | None = None) -> None:
    desc = "pi-Stomp Recovery Service"
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=desc)
    parser.add_argument("--log", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--force-crash", action="store_true", help="Force crash recovery mode")
    parser.add_argument("--force-menu", action="store_true", help="Force recovery menu mode")
    parsed: argparse.Namespace = parser.parse_args(args)

    logging.basicConfig(
        level=getattr(logging, parsed.log),
        format="%(levelname)s:%(name)s:%(message)s",
    )

    if parsed.force_crash:
        boot_mode: BootMode = BootMode.CRASH_RECOVERY
    elif parsed.force_menu:
        boot_mode = BootMode.USER_RECOVERY
    else:
        boot_mode = get_boot_mode()

    app: RecoveryApp = RecoveryApp(boot_mode)

    def handle_signal(signum: int, frame: object) -> None:
        logger.info("Received signal %d, shutting down", signum)
        app.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        app.init()
        app.run()
    except Exception:
        logger.exception("Recovery app crashed")
    finally:
        app.cleanup()


if __name__ == "__main__":
    main()
