from __future__ import annotations

import argparse
import logging
import signal
import subprocess
import time
from typing import Callable

from pistomp_recovery.config import list_config_items
from pistomp_recovery.constants import domain_for_package
from pistomp_recovery.hardware.encoder import EncoderInput
from pistomp_recovery.hardware.lcd import LcdSpi
from pistomp_recovery.items import Action, Item, Row, Target
from pistomp_recovery.packages import get_available_updates
from pistomp_recovery.packages.installer import (
    download_packages,
    install_from_cache,
    install_packages,
)
from pistomp_recovery.pedalboards import list_pedalboard_items
from pistomp_recovery.service import (
    BootMode,
    CrashInfo,
    diagnose_crash,
    get_boot_mode,
    recovery_sha,
    restart_jack,
    restart_mod,
    start_main_app,
    stop_main_app,
)
from pistomp_recovery.system import list_system_items
from pistomp_recovery.ui.display import Display
from pistomp_recovery.ui.input import InputManager
from pistomp_recovery.ui.screens import Screen
from pistomp_recovery.ui.screens.crash import CrashScreen
from pistomp_recovery.ui.screens.menu_screen import MenuScreen
from pistomp_recovery.ui.widgets.header import ICON_BACK, ICON_EXIT
from pistomp_recovery.ui.widgets.misc import InputEvent

logger = logging.getLogger(__name__)

POLL_INTERVAL: float = 0.03

# Recovery operations sharing the Pedalboards/Plugins/Config/System submenu.
MODE_CHECKPOINT: str = "checkpoint"
MODE_FACTORY: str = "factory"
MODE_UPDATES: str = "updates"

_MODE_TITLES: dict[str, str] = {
    MODE_CHECKPOINT: "Reset to Checkpoint",
    MODE_FACTORY: "Factory Reset",
    MODE_UPDATES: "Updates",
}

_DOMAINS: tuple[tuple[str, str], ...] = (
    ("pedalboards", "Pedalboards"),
    ("plugins", "Plugins"),
    ("config", "Config"),
    ("system", "System"),
)


def _reboot() -> None:
    subprocess.run(["systemctl", "reboot"], check=False)


def _power_off() -> None:
    subprocess.run(["systemctl", "poweroff"], check=False)


class RecoveryApp:
    def __init__(self, boot_mode: BootMode) -> None:
        self._boot_mode: BootMode = boot_mode
        self._running: bool = True
        self._dirty: bool = True
        self._display: Display = Display(LcdSpi())
        self._encoder: EncoderInput = EncoderInput()
        self._input: InputManager = InputManager(self._encoder)
        self._screen_stack: list[Screen] = []

    def init(self) -> None:
        stop_main_app()
        self._display.init()
        self._encoder.start()
        self._input.start()
        logger.info("Recovery app initialized (boot mode: %s)", self._boot_mode.name)

        if self._boot_mode == BootMode.CRASH_RECOVERY:
            crash_info: CrashInfo = diagnose_crash()
            screen: CrashScreen = CrashScreen(
                self._display.surface,
                on_resume=self._resume_main_app,
                on_recovery=self._show_main_menu,
                crash_info=crash_info,
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
            if self._dirty:
                self._draw_current_screen()
                self._display.update(self._display.surface)
                self._dirty = False
            time.sleep(POLL_INTERVAL)

    # -- screen stack -------------------------------------------------------

    def _push_screen(self, screen: Screen) -> None:
        self._screen_stack.append(screen)
        self._dirty = True

    def _pop_screen(self) -> None:
        if len(self._screen_stack) > 1:
            self._screen_stack.pop()
            self._dirty = True

    def _current_screen(self) -> Screen | None:
        return self._screen_stack[-1] if self._screen_stack else None

    def _handle_event(self, event: InputEvent) -> None:
        screen: Screen | None = self._current_screen()
        if screen is None:
            return
        if screen.handle_event(event):
            self._dirty = True

    def _draw_current_screen(self) -> None:
        screen: Screen | None = self._current_screen()
        if screen is not None:
            screen.draw()

    def _push_menu(
        self, title: str, rows: list[Row], back: bool
    ) -> MenuScreen:
        icon: Target = (
            Target(ICON_BACK, self._pop_screen)
            if back
            else Target(ICON_EXIT, self._resume_main_app)
        )
        screen: MenuScreen = MenuScreen(self._display.surface, title, rows, icon)
        self._push_screen(screen)
        return screen

    # -- top menu -----------------------------------------------------------

    def _show_main_menu(self) -> None:
        title: str = f"pi-Stomp! Recovery {recovery_sha()}"
        rows: list[Row] = [
            Row(
                (
                    Target("JACK", restart_jack),
                    Target("MOD", restart_mod),
                ),
                prefix="RESTART ",
            ),
            Row((Target(
                "RESET TO CHECKPOINT",
                lambda: self._show_domain_picker(MODE_CHECKPOINT),
            ),)),
            Row((Target(
                "FACTORY RESET",
                lambda: self._show_domain_picker(MODE_FACTORY),
            ),)),
            Row((Target(
                "UPDATES",
                lambda: self._show_domain_picker(MODE_UPDATES),
            ),)),
            Row((
                Target("REBOOT", _reboot, confirm="Reboot now?"),
                Target("POWER OFF", _power_off, confirm="Power off now?"),
            )),
        ]
        self._push_menu(title, rows, back=False)

    # -- shared domain picker ----------------------------------------------

    def _show_domain_picker(self, mode: str) -> None:
        rows: list[Row] = []
        for domain, label in _DOMAINS:
            count: int = len(self._domain_items(mode, domain))
            right: str = self._badge(mode, count)
            rows.append(Row(
                (Target(label, lambda m=mode, d=domain: self._show_domain(m, d)),),
                right=right,
            ))
        self._push_menu(_MODE_TITLES[mode], rows, back=True)

    @staticmethod
    def _badge(mode: str, count: int) -> str:
        if count == 0:
            return ""
        return f"{count} available" if mode == MODE_UPDATES else f"{count} changed"

    def _show_domain(self, mode: str, domain: str) -> None:
        items: list[Item] = self._domain_items(mode, domain)
        title: str = dict(_DOMAINS)[domain]
        if not items:
            empty: str = "No updates" if mode == MODE_UPDATES else "Nothing to reset"
            rows: list[Row] = [Row((Target(empty, lambda: None, enabled=False),))]
        else:
            rows = [
                Row((self._item_target(it, title),), right=it.right) for it in items
            ]
        self._push_menu(title, rows, back=True)

    # -- item / detail ------------------------------------------------------

    def _item_target(self, item: Item, parent_title: str) -> Target:
        if not item.actions:
            return Target(item.label, lambda: None, enabled=False)
        if len(item.actions) == 1:
            action = item.actions[0]
            return Target(item.label, action.callback, confirm=action.confirm)
        return Target(
            item.label, lambda it=item: self._show_item_detail(it)
        )

    def _show_item_detail(self, item: Item) -> None:
        rows: list[Row] = [
            Row((Target(a.label, a.callback, confirm=a.confirm),))
            for a in item.actions
        ]
        self._push_menu(item.label, rows, back=True)

    # -- domain item sourcing ----------------------------------------------

    def _domain_items(self, mode: str, domain: str) -> list[Item]:
        if domain == "plugins":
            return []
        if mode == MODE_UPDATES:
            return self._update_items(domain)
        raw: list[Item] = self._raw_domain_items(domain)
        wanted: str = (
            "Rollback to stamp" if mode == MODE_CHECKPOINT else "Rollback to factory"
        )
        result: list[Item] = []
        for it in raw:
            actions = [a for a in it.actions if a.label == wanted]
            if not actions:
                continue
            if mode == MODE_CHECKPOINT and not it.dirty:
                continue
            result.append(Item(it.name, it.label, it.dirty, it.right, actions))
        return result

    def _raw_domain_items(self, domain: str) -> list[Item]:
        loaders: dict[str, Callable[[], list[Item]]] = {
            "pedalboards": list_pedalboard_items,
            "config": list_config_items,
            "system": list_system_items,
        }
        loader = loaders.get(domain)
        if loader is None:
            return []
        try:
            return loader()
        except Exception:
            logger.debug("Could not list %s items", domain, exc_info=True)
            return []

    def _update_items(self, domain: str) -> list[Item]:
        try:
            updates: list[tuple[str, str, str]] = get_available_updates()
        except Exception:
            logger.debug("Could not query updates", exc_info=True)
            return []
        scoped = [u for u in updates if domain_for_package(u[0]) == domain]
        items: list[Item] = []
        for pkg, old_ver, new_ver in scoped:
            items.append(Item(
                name=pkg,
                label=f"{pkg} {old_ver}→{new_ver}",
                dirty=False,
                right=f"↑{new_ver}",
                actions=[Action(
                    f"Update to {new_ver}",
                    lambda p=pkg: self._install_packages([p]),
                    confirm=f"Update {pkg}?",
                )],
            ))
        if items:
            names = [u[0] for u in scoped]
            items.append(Item(
                name="all",
                label="Update All",
                dirty=False,
                right="",
                actions=[Action(
                    "Update All",
                    lambda ps=names: self._install_packages(ps),
                    confirm="Update all?",
                )],
            ))
        return items

    # -- package install with progress -------------------------------------

    def _install_packages(self, packages: list[str]) -> None:
        screen: Screen | None = self._current_screen()
        menu: MenuScreen | None = screen if isinstance(screen, MenuScreen) else None

        def progress(title: str, frac: float, status: str, done: bool = False) -> None:
            if menu is not None:
                menu.set_progress(title, frac, status, done=done)
                self._dirty = True

        progress("Downloading...", 0.0, f"Downloading {len(packages)} package(s)...")
        if not download_packages(packages):
            progress("Download failed", 0.0, "Download failed. Click to continue.", True)
            return

        progress("Installing...", 0.5, f"Installing {len(packages)} package(s)...")
        if not install_packages(packages):
            progress("Rolling back...", 0.5, "Install failed, rolling back...")
            install_from_cache(packages)
            progress("Install failed", 0.0, "Install failed. Click to continue.", True)
            return

        progress("Saving snapshot...", 0.9, "Saving snapshot...")
        try:
            from pistomp_recovery.packages import stamp_packages
            stamp_packages()
        except Exception:
            logger.exception("Stamp after update failed")

        progress("Update complete", 1.0, "Done. Exit (►) to restart pi-Stomp.", True)

    # -- exit ---------------------------------------------------------------

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
