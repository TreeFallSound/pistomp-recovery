"""Bootstrap the emulator — creates a live recovery UI in a pygame window.

Usage:
    python -m pistomp_recovery.emulator
    python -m pistomp_recovery.emulator --force-crash

Keyboard shortcuts:
    ← / →       navigate menu
    Enter/Space  select
    L            long press (back/cancel)
    Esc          quit
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

import pygame

from pistomp_recovery.constants import LCD_WIDTH, LCD_HEIGHT
from pistomp_recovery.emulator.controls import FakeEncoderInput, FakeInputManager
from pistomp_recovery.emulator.lcd_pygame import LcdPygame
from pistomp_recovery.emulator.window import EmulatorWindow
from pistomp_recovery.service import BootMode
from pistomp_recovery.ui.display import Display
from pistomp_recovery.ui.screens.crash import CrashScreen
from pistomp_recovery.ui.screens.main_menu import MainMenuScreen, MenuAction
from pistomp_recovery.ui.screens.config_screen import ConfigScreen
from pistomp_recovery.ui.screens.system_info import SystemInfoScreen
from pistomp_recovery.ui.screens.updates import UpdatesScreen
from pistomp_recovery.ui.widgets.misc import InputEvent
from pistomp_recovery.packages.manager import PackageManager

logger = logging.getLogger(__name__)

POLL_INTERVAL: float = 0.02


class EmulatorApp:
    def __init__(self, boot_mode: BootMode = BootMode.USER_RECOVERY) -> None:
        self._boot_mode: BootMode = boot_mode
        self._running: bool = True
        self._lcd: LcdPygame = LcdPygame()
        self._encoder: FakeEncoderInput = FakeEncoderInput()
        self._input: FakeInputManager = FakeInputManager(self._encoder)
        self._pkg_manager: PackageManager = PackageManager()
        self._current_screen: str = "crash" if boot_mode == BootMode.CRASH_RECOVERY else "menu"
        self._surface: pygame.Surface = pygame.Surface((LCD_WIDTH, LCD_HEIGHT))
        self._window: EmulatorWindow | None = None

    def init(self) -> None:
        pygame.init()
        self._lcd.init()
        self._window = EmulatorWindow(
            lcd_surface=self._surface,
            send_event=self._inject_event,
        )
        logger.info("Emulator initialized (boot mode: %s)", self._boot_mode.name)

    def _inject_event(self, event: InputEvent) -> None:
        self._input.inject_event(event)

    def run(self) -> None:
        assert self._window is not None
        while self._running:
            if not self._window.process_events():
                break

            events: list[InputEvent] = self._input.poll()
            for event in events:
                self._handle_event(event)

            self._draw_current_screen()
            self._window.render()
            time.sleep(POLL_INTERVAL)

    def _handle_event(self, event: InputEvent) -> None:
        if self._current_screen == "crash":
            screen: CrashScreen = CrashScreen(
                self._surface,
                crash_log="Traceback (most recent call last):\n  File \"modalapistomp.py\", line 42\n    handler.poll_controls()\nAttributeError: 'NoneType' object has no attribute 'poll_controls'",
                on_resume=self._resume,
                on_recovery=lambda: setattr(self, '_current_screen', 'menu'),
            )
            screen.handle_event(event)
            self._current_screen = "menu"

        elif self._current_screen == "menu":
            menu_screen: MainMenuScreen = MainMenuScreen(self._surface)
            if menu_screen.handle_event(event):
                action: MenuAction | None = menu_screen.action
                if action is not None:
                    self._on_menu_action(action)

        elif self._current_screen == "updates":
            updates_screen: UpdatesScreen = UpdatesScreen(self._surface, self._pkg_manager)
            updates_screen.check_updates()
            if event == InputEvent.LONG_CLICK:
                self._current_screen = "menu"
            else:
                updates_screen.handle_event(event)

        elif self._current_screen == "config":
            config_screen: ConfigScreen = ConfigScreen(self._surface)
            if event == InputEvent.LONG_CLICK:
                self._current_screen = "menu"
            else:
                config_screen.handle_event(event)

        elif self._current_screen == "system_info":
            info_screen: SystemInfoScreen = SystemInfoScreen(self._surface)
            info_screen.refresh()
            if event == InputEvent.LONG_CLICK:
                self._current_screen = "menu"
            else:
                info_screen.handle_event(event)

    def _on_menu_action(self, action: MenuAction) -> None:
        if action == MenuAction.RESUME:
            logger.info("Resume pressed (emulated)")
        elif action == MenuAction.SYSTEM_INFO:
            self._current_screen = "system_info"
        elif action == MenuAction.PACKAGE_UPDATES:
            self._current_screen = "updates"
        elif action == MenuAction.CONFIG_MANAGEMENT:
            self._current_screen = "config"
        elif action == MenuAction.REBOOT:
            logger.info("Reboot pressed (emulated)")
        elif action == MenuAction.POWER_OFF:
            logger.info("Power off pressed (emulated)")
            self._running = False

    def _resume(self) -> None:
        logger.info("Resume pressed (emulated)")

    def _draw_current_screen(self) -> None:
        self._surface.fill((0, 0, 0))

        if self._current_screen == "crash":
            screen: CrashScreen = CrashScreen(
                self._surface,
                crash_log="App crashed",
                on_resume=self._resume,
                on_recovery=lambda: setattr(self, '_current_screen', 'menu'),
            )
            screen.draw()
        elif self._current_screen == "menu":
            MainMenuScreen(self._surface).draw()
        elif self._current_screen == "updates":
            UpdatesScreen(self._surface, self._pkg_manager).draw()
        elif self._current_screen == "config":
            ConfigScreen(self._surface).draw()
        elif self._current_screen == "system_info":
            SystemInfoScreen(self._surface).draw()


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="pistomp-recovery emulator"
    )
    parser.add_argument("--log", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--force-crash", action="store_true", help="Start in crash recovery mode")
    args: argparse.Namespace = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log),
        format="%(levelname)s:%(name)s:%(message)s",
    )

    boot_mode: BootMode = BootMode.CRASH_RECOVERY if args.force_crash else BootMode.USER_RECOVERY
    app: EmulatorApp = EmulatorApp(boot_mode)

    try:
        app.init()
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()