"""Bootstrap the emulator — creates a live recovery UI in a pygame window.

Usage:
    python -m pistomp_recovery.emulator
    python -m pistomp_recovery.emulator --force-crash

Keyboard shortcuts:
    ← / →        navigate reticules (incl. the header back/exit icon)
    Enter/Space  select
    Esc          quit
"""

from __future__ import annotations

import argparse
import logging
import time

import pygame

from pistomp_recovery.constants import LCD_HEIGHT, LCD_WIDTH, domain_for_package
from pistomp_recovery.emulator.controls import FakeEncoderInput, FakeInputManager
from pistomp_recovery.emulator.lcd_pygame import LcdPygame
from pistomp_recovery.emulator.window import EmulatorWindow
from pistomp_recovery.items import Action, Item, Row, Target
from pistomp_recovery.service import BootMode, CrashInfo
from pistomp_recovery.ui.screens import Screen
from pistomp_recovery.ui.screens.crash import CrashScreen
from pistomp_recovery.ui.screens.menu_screen import MenuScreen
from pistomp_recovery.ui.widgets.header import ICON_BACK, ICON_EXIT
from pistomp_recovery.ui.widgets.misc import InputEvent

logger = logging.getLogger(__name__)

POLL_INTERVAL: float = 0.02

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

# ---------------------------------------------------------------------------
# Stub data covering all four states: clean stamped / dirty stamped /
# factory / unknown. Plugins is intentionally empty (no-op domain).
# ---------------------------------------------------------------------------


def _stub_actions(*labels: str) -> list[Action]:
    return [Action(label, lambda label=label: logger.info("%s (emulated)", label),
                   confirm=f"{label}?") for label in labels]


STUB_PEDALBOARDS: list[Item] = [
    Item("AmpBud.pedalboard", "AmpBud.pedalboard", True, "2d ago",
         _stub_actions("Rollback to stamp", "Rollback to factory")),
    Item("Beths.pedalboard", "Beths.pedalboard", False, "✓ 3d ago",
         _stub_actions("Rollback to stamp", "Rollback to factory")),
    Item("Carbon-Copy.pedalboard", "Carbon-Copy.pedalboard", True, "?",
         _stub_actions("Rollback to factory")),
    Item("factory-defaults.pedalboard", "factory-defaults.pedalboard", False,
         "factory", _stub_actions("Rollback to factory")),
]

STUB_CONFIG: list[Item] = [
    Item("settings.yml", "settings.yml", True, "2d ago",
         _stub_actions("Rollback to stamp", "Rollback to factory")),
    Item("default_config.yml", "default_config.yml", False, "factory",
         _stub_actions("Rollback to factory")),
]

STUB_SYSTEM: list[Item] = [
    Item("config.txt", "config.txt", True, "5d ago",
         _stub_actions("Rollback to stamp", "Rollback to factory")),
    Item("jackdrc", "jackdrc", False, "factory",
         _stub_actions("Rollback to factory")),
]

STUB_PLUGINS: list[Item] = []

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
        self._dirty: bool = True

    def init(self) -> None:
        pygame.init()
        self._lcd.init()
        self._window = EmulatorWindow(
            lcd_surface=self._surface,
            send_event=self._inject_event,
        )
        logger.info("Emulator initialized (boot mode: %s)", self._boot_mode.name)

        if self._boot_mode == BootMode.CRASH_RECOVERY:
            crash_info: CrashInfo = CrashInfo(
                boot_mode=BootMode.CRASH_RECOVERY,
                failed_service="mod-host",
                crash_log=(
                    "Traceback (most recent call last):\n"
                    "  File 'modalapistomp.py', line 42\n"
                    "    handler.poll_controls()\n"
                    "AttributeError: 'NoneType' object"
                    " has no attribute 'poll_controls'"
                ),
                service_states={
                    "jack": "active",
                    "mod-host": "failed",
                    "mod-ui": "inactive",
                    "mod-ala-pi-stomp": "inactive",
                },
            )
            self._push_screen(CrashScreen(
                self._surface,
                on_resume=self._resume,
                on_recovery=self._show_main_menu,
                crash_info=crash_info,
            ))
        else:
            self._show_main_menu()

    # -- screen stack -------------------------------------------------------

    def _inject_event(self, event: InputEvent) -> None:
        self._input.inject_event(event)

    def _push_screen(self, screen: Screen) -> None:
        self._screen_stack.append(screen)
        self._dirty = True

    def _pop_screen(self) -> None:
        if len(self._screen_stack) > 1:
            self._screen_stack.pop()
            self._dirty = True

    def _push_menu(self, title: str, rows: list[Row], back: bool) -> MenuScreen:
        icon: Target = (
            Target(ICON_BACK, self._pop_screen)
            if back
            else Target(ICON_EXIT, self._resume)
        )
        screen: MenuScreen = MenuScreen(self._surface, title, rows, icon)
        self._push_screen(screen)
        return screen

    # -- menus --------------------------------------------------------------

    def _show_main_menu(self) -> None:
        title: str = "pi-Stomp! Recovery 0a1b2c3"
        rows: list[Row] = [
            Row((
                Target("JACK", lambda: logger.info("Restart JACK (emulated)")),
                Target("MOD", lambda: logger.info("Restart MOD (emulated)")),
            ), prefix="RESTART "),
            Row((Target("RESET TO CHECKPOINT",
                        lambda: self._show_domain_picker(MODE_CHECKPOINT)),)),
            Row((Target("FACTORY RESET",
                        lambda: self._show_domain_picker(MODE_FACTORY)),)),
            Row((Target("UPDATES",
                        lambda: self._show_domain_picker(MODE_UPDATES)),)),
            Row((
                Target("REBOOT", lambda: logger.info("Reboot (emulated)"),
                       confirm="Reboot now?"),
                Target("POWER OFF", lambda: setattr(self, "_running", False),
                       confirm="Power off now?"),
            )),
        ]
        self._push_menu(title, rows, back=False)

    def _show_domain_picker(self, mode: str) -> None:
        rows: list[Row] = []
        for domain, label in _DOMAINS:
            count: int = len(self._domain_items(mode, domain))
            right: str = ""
            if count:
                right = f"{count} available" if mode == MODE_UPDATES else f"{count} changed"
            rows.append(Row(
                (Target(label, lambda m=mode, d=domain: self._show_domain(m, d)),),
                right=right,
            ))
        self._push_menu(_MODE_TITLES[mode], rows, back=True)

    def _show_domain(self, mode: str, domain: str) -> None:
        items: list[Item] = self._domain_items(mode, domain)
        title: str = dict(_DOMAINS)[domain]
        if not items:
            empty: str = "No updates" if mode == MODE_UPDATES else "Nothing to reset"
            rows: list[Row] = [Row((Target(empty, lambda: None, enabled=False),))]
        else:
            rows = [Row((self._item_target(it),), right=it.right) for it in items]
        self._push_menu(title, rows, back=True)

    def _item_target(self, item: Item) -> Target:
        if not item.actions:
            return Target(item.label, lambda: None, enabled=False)
        if len(item.actions) == 1:
            action = item.actions[0]
            return Target(item.label, action.callback, confirm=action.confirm)
        return Target(item.label, lambda it=item: self._show_item_detail(it))

    def _show_item_detail(self, item: Item) -> None:
        rows: list[Row] = [
            Row((Target(a.label, a.callback, confirm=a.confirm),))
            for a in item.actions
        ]
        self._push_menu(item.label, rows, back=True)

    # -- data ---------------------------------------------------------------

    def _domain_items(self, mode: str, domain: str) -> list[Item]:
        if domain == "plugins":
            return list(STUB_PLUGINS)
        if mode == MODE_UPDATES:
            return self._update_items(domain)
        loaders: dict[str, list[Item]] = {
            "pedalboards": STUB_PEDALBOARDS,
            "config": STUB_CONFIG,
            "system": STUB_SYSTEM,
        }
        raw: list[Item] = loaders.get(domain, [])
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

    def _update_items(self, domain: str) -> list[Item]:
        scoped = [u for u in STUB_UPDATES if domain_for_package(u[0]) == domain]
        items: list[Item] = []
        for pkg, old_ver, new_ver in scoped:
            items.append(Item(
                pkg, f"{pkg} {old_ver}→{new_ver}", False, f"↑{new_ver}",
                [Action(f"Update to {new_ver}",
                        lambda p=pkg: logger.info("Install %s (emulated)", p),
                        confirm=f"Update {pkg}?")],
            ))
        if items:
            items.append(Item(
                "all", "Update All", False, "",
                [Action("Update All",
                        lambda: logger.info("Install all (emulated)"),
                        confirm="Update all?")],
            ))
        return items

    def _resume(self) -> None:
        logger.info("Resume pressed (emulated)")

    # -- loop ---------------------------------------------------------------

    def run(self) -> None:
        assert self._window is not None
        while self._running:
            if not self._window.process_events():
                break
            events: list[InputEvent] = self._input.poll()
            for event in events:
                self._handle_event(event)
            if self._dirty:
                self._draw_current_screen()
                self._window.render()
                self._dirty = False
            time.sleep(POLL_INTERVAL)

    def _handle_event(self, event: InputEvent) -> None:
        screen: Screen | None = self._screen_stack[-1] if self._screen_stack else None
        if screen is None:
            return
        if screen.handle_event(event):
            self._dirty = True

    def _draw_current_screen(self) -> None:
        screen: Screen | None = self._screen_stack[-1] if self._screen_stack else None
        if screen is not None:
            screen.draw()


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="pistomp-recovery emulator"
    )
    parser.add_argument("--log", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--force-crash", action="store_true",
                        help="Start in crash recovery mode")
    args: argparse.Namespace = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log),
        format="%(levelname)s:%(name)s:%(message)s",
    )

    boot_mode: BootMode = (
        BootMode.CRASH_RECOVERY if args.force_crash else BootMode.USER_RECOVERY
    )
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
