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
import time
from datetime import datetime, timezone
from pathlib import Path

import pygame

from pistomp_recovery.constants import LCD_HEIGHT, LCD_WIDTH
from pistomp_recovery.emulator.controls import FakeEncoderInput, FakeInputManager
from pistomp_recovery.emulator.lcd_pygame import LcdPygame
from pistomp_recovery.emulator.window import EmulatorWindow
from pistomp_recovery.facets.packages_facet import PackageItem
from pistomp_recovery.facets.pedalboards_facet import PedalboardItem
from pistomp_recovery.service import BootMode
from pistomp_recovery.ui.screens import Screen
from pistomp_recovery.ui.screens.crash import CrashScreen
from pistomp_recovery.ui.screens.main_menu import MainMenuScreen
from pistomp_recovery.ui.screens.packages_screen import PackagesScreen
from pistomp_recovery.ui.screens.pedalboards_screen import PedalboardsScreen
from pistomp_recovery.ui.screens.reset_screen import DirtyItem, ResetScreen
from pistomp_recovery.ui.screens.system_info import SystemInfoScreen
from pistomp_recovery.ui.screens.types import Actions
from pistomp_recovery.ui.screens.updates import UpdatesScreen
from pistomp_recovery.ui.widgets.confirm_dialog import ConfirmDialog
from pistomp_recovery.ui.widgets.misc import InputEvent

logger = logging.getLogger(__name__)

POLL_INTERVAL: float = 0.02

STUB_PEDALBOARDS: list[PedalboardItem] = [
    PedalboardItem(
        name="AmpBud.pedalboard",
        path=Path("/tmp/stub/AmpBud.pedalboard"),
        is_dirty=True,
        last_stamp_time=datetime(2026, 6, 9, 10, 0, tzinfo=timezone.utc),
        last_stamp_tag="stamp/pedalboard/AmpBud.pedalboard/20260609-100000",
    ),
    PedalboardItem(
        name="Beths.pedalboard",
        path=Path("/tmp/stub/Beths.pedalboard"),
        is_dirty=False,
        last_stamp_time=datetime(2026, 6, 8, 14, 30, tzinfo=timezone.utc),
        last_stamp_tag="stamp/pedalboard/Beths.pedalboard/20260608-143000",
    ),
    PedalboardItem(
        name="Carbon-Copy.pedalboard",
        path=Path("/tmp/stub/Carbon-Copy.pedalboard"),
        is_dirty=True,
        last_stamp_time=datetime(2026, 6, 7, 20, 0, tzinfo=timezone.utc),
        last_stamp_tag="stamp/pedalboard/Carbon-Copy.pedalboard/20260607-200000",
    ),
    PedalboardItem(
        name="factory-defaults.pedalboard",
        path=Path("/tmp/stub/factory-defaults.pedalboard"),
        is_dirty=False,
        last_stamp_time=None,
        last_stamp_tag=None,
    ),
]

STUB_PACKAGES: list[PackageItem] = [
    PackageItem(
        name="jack2-pistomp",
        installed_version="1.9.12",
        stamped_version="1.9.11",
        factory_version="1.9.10",
        available_version="1.9.13",
        last_stamp_time=datetime(2026, 6, 8, tzinfo=timezone.utc),
    ),
    PackageItem(
        name="mod-ui",
        installed_version="0.13.0",
        stamped_version="0.13.0",
        factory_version="0.12.0",
        available_version="0.14.0",
        last_stamp_time=datetime(2026, 6, 7, tzinfo=timezone.utc),
    ),
    PackageItem(
        name="pi-stomp",
        installed_version="2.4.1",
        stamped_version="2.4.1",
        factory_version="2.4.0",
        available_version=None,
        last_stamp_time=datetime(2026, 6, 6, tzinfo=timezone.utc),
    ),
]

STUB_UPDATES: list[tuple[str, str, str]] = [
    ("jack2-pistomp", "1.9.12", "1.9.13"),
    ("mod-ui", "0.13.0", "0.14.0"),
]


class EmulatorApp:
    def __init__(self, boot_mode: BootMode = BootMode.USER_RECOVERY) -> None:
        self._boot_mode: BootMode = boot_mode
        self._running: bool = True
        self._lcd: LcdPygame = LcdPygame()
        self._encoder: FakeEncoderInput = FakeEncoderInput()
        self._input: FakeInputManager = FakeInputManager(self._encoder)
        self._surface: pygame.Surface = pygame.Surface((LCD_WIDTH, LCD_HEIGHT))
        self._window: EmulatorWindow | None = None
        self._screen_stack: list[Screen] = []
        self._confirm_active: bool = False
        self._confirm_dialog: ConfirmDialog | None = None

    def init(self) -> None:
        pygame.init()
        self._lcd.init()
        self._window = EmulatorWindow(
            lcd_surface=self._surface,
            send_event=self._inject_event,
        )
        logger.info("Emulator initialized (boot mode: %s)", self._boot_mode.name)

        if self._boot_mode == BootMode.CRASH_RECOVERY:
            screen: CrashScreen = CrashScreen(
                self._surface,
                crash_log=(
                    "Traceback (most recent call last):\n"
                    '  File "modalapistomp.py", line 42\n'
                    "    handler.poll_controls()\n"
                    "AttributeError: 'NoneType' object"
                    " has no attribute 'poll_controls'"
                ),
                on_resume=self._resume,
                on_recovery=self._show_main_menu,
            )
            self._push_screen(screen)
        else:
            self._show_main_menu()

    def _inject_event(self, event: InputEvent) -> None:
        self._input.inject_event(event)

    def _push_screen(self, screen: Screen) -> None:
        screen.set_back_callback(self._pop_screen)
        self._screen_stack.append(screen)

    def _pop_screen(self) -> None:
        if len(self._screen_stack) > 1:
            self._screen_stack.pop()

    def _show_main_menu(self) -> None:
        dirty: int = sum(1 for p in STUB_PEDALBOARDS if p.is_dirty)
        dirty += sum(1 for p in STUB_PACKAGES if p.is_dirty)
        updates: int = sum(1 for p in STUB_PACKAGES if p.available_version is not None)

        actions: Actions = {
            "resume": self._resume,
            "reset": self._show_reset,
            "update": self._show_updates,
            "pedalboards": self._show_pedalboards,
            "packages": self._show_packages,
            "system_info": self._show_system_info,
            "reboot": lambda: logger.info("Reboot (emulated)"),
            "power_off": lambda: setattr(self, "_running", False),
        }
        menu: MainMenuScreen = MainMenuScreen(
            self._surface,
            actions=actions,
            dirty_count=dirty,
            update_count=updates,
        )
        self._push_screen(menu)

    def _show_reset(self) -> None:
        items: list[DirtyItem] = []
        for pb in STUB_PEDALBOARDS:
            if pb.is_dirty:
                items.append(
                    DirtyItem(
                        label=pb.display_label,
                        right=pb.display_right,
                        kind="pedalboard",
                        name=pb.name,
                    )
                )
        for pkg in STUB_PACKAGES:
            if pkg.is_dirty:
                drift: str = pkg.version_drift
                right: str = f"{drift}  {pkg.display_time}" if drift else pkg.display_time
                items.append(
                    DirtyItem(
                        label=pkg.display_name,
                        right=right,
                        kind="package",
                        name=pkg.name,
                    )
                )

        screen: ResetScreen = ResetScreen(
            self._surface,
            items,
            on_rollback_stamp=lambda k, n: logger.info("Rollback stamp: %s %s (emulated)", k, n),
            on_rollback_factory=lambda k, n: logger.info(
                "Rollback factory: %s %s (emulated)", k, n
            ),
        )
        self._push_screen(screen)

    def _show_updates(self) -> None:
        screen: UpdatesScreen = UpdatesScreen(
            self._surface,
            STUB_UPDATES,
            on_install=lambda pkgs: logger.info("Install all: %s (emulated)", pkgs),
            on_install_single=lambda pkg: logger.info("Install single: %s (emulated)", pkg),
        )
        self._push_screen(screen)

    def _show_pedalboards(self) -> None:
        screen: PedalboardsScreen = PedalboardsScreen(
            self._surface,
            STUB_PEDALBOARDS,
            on_stamp=lambda n: logger.info("Stamp pedalboard: %s (emulated)", n),
            on_rollback_stamp=lambda n: logger.info("Rollback stamp: %s (emulated)", n),
            on_rollback_factory=lambda n: logger.info("Rollback factory: %s (emulated)", n),
        )
        self._push_screen(screen)

    def _show_packages(self) -> None:
        screen: PackagesScreen = PackagesScreen(
            self._surface,
            STUB_PACKAGES,
            pending_restart=["jack", "mod-host"],
            on_stamp=lambda n: logger.info("Stamp package: %s (emulated)", n),
            on_rollback_stamp=lambda n: logger.info("Rollback stamp: %s (emulated)", n),
            on_rollback_factory=lambda n: logger.info("Rollback factory: %s (emulated)", n),
            on_update=lambda n: logger.info("Update package: %s (emulated)", n),
            on_restart_services=lambda: logger.info("Restart services (emulated)"),
        )
        self._push_screen(screen)

    def _show_system_info(self) -> None:
        screen: SystemInfoScreen = SystemInfoScreen(self._surface)
        screen.refresh()
        self._push_screen(screen)

    def _resume(self) -> None:
        logger.info("Resume pressed (emulated)")

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
        screen: Screen | None = self._screen_stack[-1] if self._screen_stack else None
        if screen is None:
            return

        if self._confirm_active and self._confirm_dialog is not None:
            self._confirm_dialog.handle_event(event)
            return

        if not screen.handle_event(event):
            if event == InputEvent.LONG_CLICK:
                self._pop_screen()

    def _draw_current_screen(self) -> None:
        screen: Screen | None = self._screen_stack[-1] if self._screen_stack else None
        if screen is None:
            return
        screen.draw()


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
