from __future__ import annotations

import argparse
import logging
import signal
import subprocess
import time
from typing import Callable

from pistomp_recovery.facets.base import Facet
from pistomp_recovery.facets.config_facet import ConfigFacet
from pistomp_recovery.facets.packages_facet import PackageItem, PackagesFacet
from pistomp_recovery.facets.pedalboards_facet import PedalboardItem, PedalboardsFacet
from pistomp_recovery.facets.system_facet import SystemFacet
from pistomp_recovery.hardware.encoder import EncoderInput
from pistomp_recovery.hardware.lcd import LcdSpi
from pistomp_recovery.packages.health import full_health_check
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
from pistomp_recovery.ui.screens import Screen
from pistomp_recovery.ui.screens.crash import CrashScreen
from pistomp_recovery.ui.screens.main_menu import MainMenuScreen
from pistomp_recovery.ui.screens.packages_screen import PackagesScreen
from pistomp_recovery.ui.screens.pedalboards_screen import PedalboardsScreen
from pistomp_recovery.ui.screens.reset_screen import DirtyItem, ResetScreen
from pistomp_recovery.ui.screens.system_info import SystemInfoScreen
from pistomp_recovery.ui.screens.updates import UpdatesScreen
from pistomp_recovery.ui.widgets.confirm_dialog import ConfirmDialog
from pistomp_recovery.ui.widgets.misc import InputEvent

logger = logging.getLogger(__name__)

POLL_INTERVAL: float = 0.03


def _reboot() -> None:
    subprocess.run(["systemctl", "reboot"], check=False)


def _power_off() -> None:
    subprocess.run(["systemctl", "poweroff"], check=False)


class RecoveryApp:
    def __init__(self, boot_mode: BootMode) -> None:
        self._boot_mode: BootMode = boot_mode
        self._running: bool = True
        self._lcd: LcdSpi = LcdSpi()
        self._encoder: EncoderInput = EncoderInput()
        self._input: InputManager = InputManager(self._encoder)
        self._display: Display = Display(self._lcd)
        self._pkg_manager: PackageManager = PackageManager()
        self._ped_facet: PedalboardsFacet = PedalboardsFacet()
        self._pkg_facet: PackagesFacet = PackagesFacet()
        self._facets: dict[str, Facet] = {
            "config": ConfigFacet(),
            "pedalboards": self._ped_facet,
            "packages": self._pkg_facet,
            "system": SystemFacet(),
        }
        self._screen_stack: list[Screen] = []
        self._confirm_active: bool = False
        self._confirm_dialog: ConfirmDialog | None = None

    def init(self) -> None:
        stop_main_app()
        self._display.init()
        self._encoder.start()
        self._input.start()
        logger.info("Recovery app initialized (boot mode: %s)", self._boot_mode.name)

        if self._boot_mode == BootMode.CRASH_RECOVERY:
            screen: CrashScreen = CrashScreen(
                self._display.surface,
                crash_log=get_crash_log(),
                on_resume=self._resume_main_app,
                on_recovery=self._show_main_menu,
            )
            self._push_screen(screen)
        else:
            self._show_main_menu()

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        while self._running:
            events: list[InputEvent] = self._input.poll()
            for event in events:
                self._handle_event(event)
            self._draw_current_screen()
            time.sleep(POLL_INTERVAL)

    def _push_screen(self, screen: Screen) -> None:
        screen.set_back_callback(self._pop_screen)
        self._screen_stack.append(screen)

    def _pop_screen(self) -> None:
        if len(self._screen_stack) > 1:
            self._screen_stack.pop()

    def _current_screen(self) -> Screen | None:
        return self._screen_stack[-1] if self._screen_stack else None

    def _handle_event(self, event: InputEvent) -> None:
        screen: Screen | None = self._current_screen()
        if screen is None:
            return

        if self._confirm_active and self._confirm_dialog is not None:
            self._confirm_dialog.handle_event(event)
            return

        if not screen.handle_event(event):
            if event == InputEvent.LONG_CLICK:
                self._pop_screen()

    def _draw_current_screen(self) -> None:
        screen: Screen | None = self._current_screen()
        if screen is None:
            return
        screen.draw()
        if self._confirm_active and self._confirm_dialog is not None:
            self._confirm_dialog.draw()
        self._display.update(self._display.surface)

    def _show_main_menu(self) -> None:
        dirty_count: int = 0
        update_count: int = 0
        try:
            if self._ped_facet.path.exists():
                pb_items = self._ped_facet.list_items()
                dirty_count += sum(1 for i in pb_items if i.is_dirty)
            pkg_items = self._pkg_facet.list_items()
            dirty_count += sum(1 for i in pkg_items if i.is_dirty)
            updates: list[tuple[str, str, str]] = self._pkg_facet.get_available_updates()
            update_count = len(updates)
        except Exception:
            logger.debug("Could not query dirty/update counts", exc_info=True)

        actions: dict[str, Callable[[], None]] = {
            "resume": self._resume_main_app,
            "reset": self._show_reset,
            "update": self._show_updates,
            "pedalboards": self._show_pedalboards,
            "packages": self._show_packages,
            "system_info": self._show_system_info,
            "reboot": _reboot,
            "power_off": _power_off,
        }
        menu: MainMenuScreen = MainMenuScreen(
            self._display.surface,
            actions=actions,
            dirty_count=dirty_count,
            update_count=update_count,
        )
        self._push_screen(menu)

    def _show_reset(self) -> None:
        items: list[DirtyItem] = []
        try:
            if self._ped_facet.path.exists():
                for pb in self._ped_facet.list_items():
                    if pb.is_dirty:
                        items.append(
                            DirtyItem(
                                label=pb.display_label,
                                right=pb.display_right,
                                kind="pedalboard",
                                name=pb.name,
                            )
                        )
            for pkg in self._pkg_facet.list_items():
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
        except Exception:
            logger.debug("Could not query dirty items", exc_info=True)

        items.sort(key=lambda i: i.right, reverse=True)
        screen: ResetScreen = ResetScreen(
            self._display.surface,
            items,
            on_rollback_stamp=self._rollback_dirty_stamp,
            on_rollback_factory=self._rollback_dirty_factory,
        )
        self._push_screen(screen)

    def _show_updates(self) -> None:
        updates: list[tuple[str, str, str]] = []
        try:
            updates = self._pkg_facet.get_available_updates()
        except Exception:
            logger.debug("Could not query updates", exc_info=True)

        screen: UpdatesScreen = UpdatesScreen(
            self._display.surface,
            updates,
            on_install=self._install_packages,
            on_install_single=self._install_single_package,
        )
        self._push_screen(screen)

    def _show_pedalboards(self) -> None:
        pb_items: list[PedalboardItem] = []
        try:
            if self._ped_facet.path.exists():
                raw = self._ped_facet.list_items()
                pb_items = [i for i in raw if isinstance(i, PedalboardItem)]
        except Exception:
            logger.debug("Could not list pedalboards", exc_info=True)

        screen: PedalboardsScreen = PedalboardsScreen(
            self._display.surface,
            pb_items,
            on_stamp=self._stamp_pedalboard,
            on_rollback_stamp=self._rollback_pedalboard_stamp,
            on_rollback_factory=self._rollback_pedalboard_factory,
        )
        self._push_screen(screen)

    def _show_packages(self) -> None:
        pkg_items: list[PackageItem] = []
        try:
            raw = self._pkg_facet.list_items()
            pkg_items = [i for i in raw if isinstance(i, PackageItem)]
        except Exception:
            logger.debug("Could not list packages", exc_info=True)

        screen: PackagesScreen = PackagesScreen(
            self._display.surface,
            pkg_items,
            pending_restart=[],
            on_stamp=self._stamp_package,
            on_rollback_stamp=self._rollback_package_stamp,
            on_rollback_factory=self._rollback_package_factory,
            on_update=self._install_single_package,
            on_restart_services=self._restart_services,
        )
        self._push_screen(screen)

    def _show_system_info(self) -> None:
        screen: SystemInfoScreen = SystemInfoScreen(self._display.surface)
        screen.refresh()
        self._push_screen(screen)

    def _confirm_factory_reset(self) -> None:
        self._confirm_active = True
        self._confirm_dialog = ConfirmDialog(
            self._display.surface,
            "Factory reset\nall data?",
            self._do_factory_reset,
            self._cancel_confirm,
        )

    def _cancel_confirm(self) -> None:
        self._confirm_active = False
        self._confirm_dialog = None

    def _do_factory_reset(self) -> None:
        self._confirm_active = False
        self._confirm_dialog = None
        try:
            for facet in self._facets.values():
                facet.init()
                facet.factory_reset()
        except Exception:
            logger.exception("Factory reset failed")
        subprocess.run(["systemctl", "reboot"], check=False)

    def _rollback_dirty_stamp(self, kind: str, name: str) -> None:
        try:
            if kind == "pedalboard":
                self._ped_facet.init()
                self._ped_facet.rollback_item(name)
            elif kind == "package":
                self._pkg_facet.init()
                self._pkg_facet.rollback_item(name)
        except Exception:
            logger.exception("Rollback to stamp failed for %s %s", kind, name)

    def _rollback_dirty_factory(self, kind: str, name: str) -> None:
        try:
            if kind == "pedalboard":
                self._ped_facet.init()
                self._ped_facet.factory_reset_item(name)
            elif kind == "package":
                self._pkg_facet.init()
                self._pkg_facet.factory_reset_item(name)
        except Exception:
            logger.exception("Factory rollback failed for %s %s", kind, name)

    def _stamp_pedalboard(self, name: str) -> None:
        try:
            self._ped_facet.init()
            self._ped_facet.stamp_item(name)
        except Exception:
            logger.exception("Stamp failed for pedalboard %s", name)

    def _rollback_pedalboard_stamp(self, name: str) -> None:
        self._rollback_dirty_stamp("pedalboard", name)

    def _rollback_pedalboard_factory(self, name: str) -> None:
        self._rollback_dirty_factory("pedalboard", name)

    def _stamp_package(self, name: str) -> None:
        try:
            self._pkg_facet.init()
            self._pkg_facet.stamp()
        except Exception:
            logger.exception("Stamp failed for packages")

    def _rollback_package_stamp(self, name: str) -> None:
        self._rollback_dirty_stamp("package", name)

    def _rollback_package_factory(self, name: str) -> None:
        self._rollback_dirty_factory("package", name)

    def _install_packages(self, packages: list[str]) -> None:
        screen: Screen | None = self._current_screen()
        updates_screen: UpdatesScreen | None = None
        if isinstance(screen, UpdatesScreen):
            updates_screen = screen

        if updates_screen is not None:
            updates_screen.set_state(
                "downloading",
                0.0,
                f"Downloading {len(packages)} packages...",
            )
        if not self._pkg_manager.download_packages(packages):
            if updates_screen is not None:
                updates_screen.set_state("error", 0.0, "Download failed")
            return

        if updates_screen is not None:
            updates_screen.set_state(
                "installing",
                0.5,
                f"Installing {len(packages)} packages...",
            )
        if not self._pkg_manager.install_packages(packages):
            if updates_screen is not None:
                updates_screen.set_state(
                    "rolling_back",
                    0.5,
                    "Install failed, rolling back...",
                )
            self._pkg_manager.install_from_cache(packages)
            if updates_screen is not None:
                updates_screen.set_state("error", 0.0, "Install failed")
            return

        if updates_screen is not None:
            updates_screen.set_state(
                "health_check",
                0.75,
                "Verifying services...",
            )
        results: dict[str, bool] = full_health_check()
        if not all(results.values()):
            if updates_screen is not None:
                updates_screen.set_state(
                    "rolling_back",
                    0.75,
                    "Health check failed, rolling back...",
                )
            self._pkg_manager.install_from_cache(packages)
            if updates_screen is not None:
                updates_screen.set_state(
                    "error",
                    0.0,
                    "Health check failed",
                )
            return

        if updates_screen is not None:
            updates_screen.set_state(
                "stamping",
                0.9,
                "Saving snapshot...",
            )
        try:
            self._pkg_facet.init()
            self._pkg_facet.stamp()
        except Exception:
            logger.exception("Stamp after update failed")

        if updates_screen is not None:
            updates_screen.set_state("done", 1.0, "Update complete")

    def _install_single_package(self, pkg: str) -> None:
        self._install_packages([pkg])

    def _restart_services(self) -> None:
        try:
            start_main_app()
            self._running = False
        except Exception:
            logger.exception("Service restart failed")

    def _resume_main_app(self) -> None:
        logger.info("Resuming main app")
        start_main_app()
        self._running = False

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
