"""Emulator backends for the recovery UI.

These mirror the real device backends but use a pygame window, fake input,
and in-memory stub data that mutates when the user triggers installs or
rollbacks.  Each `EmulatorDataBackend` instance owns its own stub state so
multiple emulator instances do not share global mutable data.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import pygame

from pistomp_recovery.backends import (
    DataBackend,
    DisplayBackend,
    InputBackend,
    ProgressCallback,
    ServiceBackend,
)
from pistomp_recovery.constants import LCD_HEIGHT, LCD_WIDTH, domain_for_package
from pistomp_recovery.emulator.controls import FakeEncoderInput, FakeInputManager
from pistomp_recovery.items import Action, Item, PackageUpdate
from pistomp_recovery.service import BootMode, CrashInfo
from pistomp_recovery.ui.widgets.misc import InputEvent

logger = logging.getLogger(__name__)


class PygameDisplayBackend(DisplayBackend):
    """Pygame window surface for macOS/Linux development."""

    def __init__(self) -> None:
        self._surface: pygame.Surface = pygame.Surface((LCD_WIDTH, LCD_HEIGHT))

    @property
    def surface(self) -> pygame.Surface:
        return self._surface

    def init(self) -> None:
        self._surface.fill((0, 0, 0))

    def update(self, surface: pygame.Surface) -> None:
        # The core already draws into self._surface; the emulator window reads
        # from the same reference, so no copy is needed here.
        if surface is not self._surface:
            self._surface.blit(surface, (0, 0))


class FakeInputBackend(InputBackend):
    """Keyboard-driven fake encoder + switch input."""

    def __init__(self, encoder: FakeEncoderInput) -> None:
        self._encoder: FakeEncoderInput = encoder
        self._input: FakeInputManager = FakeInputManager(self._encoder)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def poll(self) -> list[InputEvent]:
        return self._input.poll()

    def inject_event(self, event: InputEvent) -> None:
        self._input.inject_event(event)


def _empty_items() -> list[Item]:
    return []


def _empty_updates() -> list[PackageUpdate]:
    return []


@dataclass
class StubItemState:
    """Mutable stub state for one recoverable domain."""

    items: list[Item] = field(default_factory=_empty_items)
    updates: list[PackageUpdate] = field(default_factory=_empty_updates)


class EmulatorDataBackend(DataBackend):
    """In-memory data that behaves like pacman/git for the emulator."""

    def __init__(self) -> None:
        self._state: dict[str, StubItemState] = {
            "pedalboards": StubItemState(items=self._make_pedalboard_items()),
            "config": StubItemState(items=self._make_config_items()),
            "system": StubItemState(items=self._make_system_items()),
            "plugins": StubItemState(),
        }
        self._state["system"].updates = [
            PackageUpdate("jack2-pistomp", "1.9.12", "1.9.13"),
            PackageUpdate("mod-ui", "0.13.0", "0.14.0"),
        ]

    @staticmethod
    def _mark_clean(item: Item) -> None:
        item.dirty = False
        item.right = "✓ just now"

    @staticmethod
    def _mark_factory(item: Item) -> None:
        item.dirty = False
        item.right = "factory"
        # Once an item is reset to factory it is the baseline; there is nothing
        # left to roll back to, so remove all actions and hide it from the lists.
        item.actions = []

    @classmethod
    def _stub_actions(cls, item: Item, *labels: str) -> list[Action]:
        actions: list[Action] = []
        for label in labels:
            def make_cb(lbl: str = label, it: Item = item) -> Callable[[], None]:
                if lbl == "Rollback to stamp":
                    return lambda: cls._mark_clean(it)
                if lbl == "Rollback to factory":
                    return lambda: cls._mark_factory(it)
                return lambda label=lbl: logger.info("%s (emulated)", label)

            actions.append(Action(label, make_cb(), confirm=f"{label}?"))
        return actions

    def _make_pedalboard_items(self) -> list[Item]:
        dirty_item = Item(
            "AmpBud.pedalboard", "AmpBud.pedalboard", True, "2d ago", []
        )
        clean_item = Item(
            "Beths.pedalboard", "Beths.pedalboard", False, "✓ 3d ago", []
        )
        unknown_item = Item(
            "Carbon-Copy.pedalboard", "Carbon-Copy.pedalboard", True, "?", []
        )
        factory_item = Item(
            "factory-defaults.pedalboard",
            "factory-defaults.pedalboard",
            False,
            "factory",
            [],
        )
        dirty_item.actions = self._stub_actions(
            dirty_item, "Rollback to stamp", "Rollback to factory"
        )
        clean_item.actions = self._stub_actions(
            clean_item, "Rollback to stamp", "Rollback to factory"
        )
        unknown_item.actions = self._stub_actions(
            unknown_item, "Rollback to factory"
        )
        factory_item.actions = self._stub_actions(
            factory_item, "Rollback to factory"
        )
        return [dirty_item, clean_item, unknown_item, factory_item]

    def _make_config_items(self) -> list[Item]:
        dirty_item = Item(
            "settings.yml", "settings.yml", True, "2d ago", []
        )
        factory_item = Item(
            "default_config.yml", "default_config.yml", False, "factory", []
        )
        dirty_item.actions = self._stub_actions(
            dirty_item, "Rollback to stamp", "Rollback to factory"
        )
        factory_item.actions = self._stub_actions(
            factory_item, "Rollback to factory"
        )
        return [dirty_item, factory_item]

    def _make_system_items(self) -> list[Item]:
        dirty_item = Item(
            "config.txt", "config.txt", True, "5d ago", []
        )
        factory_item = Item(
            "jackdrc", "jackdrc", False, "factory", []
        )
        dirty_item.actions = self._stub_actions(
            dirty_item, "Rollback to stamp", "Rollback to factory"
        )
        factory_item.actions = self._stub_actions(
            factory_item, "Rollback to factory"
        )
        return [dirty_item, factory_item]

    def domains(self) -> tuple[tuple[str, str], ...]:
        return (
            ("pedalboards", "Pedalboards"),
            ("plugins", "Plugins"),
            ("config", "Config"),
            ("system", "System"),
        )

    def domain_items(self, mode: str, domain: str) -> list[Item]:
        if domain == "plugins":
            return []
        state = self._state.get(domain)
        if state is None:
            return []
        if mode == "updates":
            return self._update_items(state, domain)

        raw = list(state.items)
        wanted = (
            "Rollback to stamp" if mode == "checkpoint" else "Rollback to factory"
        )
        result: list[Item] = []
        for it in raw:
            actions = [a for a in it.actions if a.label == wanted]
            if not actions:
                continue
            if mode == "checkpoint" and not it.dirty:
                continue
            result.append(Item(it.name, it.label, it.dirty, it.right, actions))
        return result

    def available_updates(self, domain: str) -> list[PackageUpdate]:
        state = self._state.get(domain)
        if state is None:
            return []
        return [u for u in state.updates if domain_for_package(u.name) == domain]

    def _update_items(self, state: StubItemState, domain: str) -> list[Item]:
        scoped = [
            u for u in state.updates if domain_for_package(u.name) == domain
        ]
        return [
            Item(
                u.name,
                f"{u.name} {u.old_version}",
                False,
                f"↑{u.new_version}",
                [],
            )
            for u in scoped
        ]

    def install_packages(
        self,
        packages: list[str],
        progress: ProgressCallback,
    ) -> bool:
        """Simulate download + install on a worker thread."""

        def step(steps: int) -> None:
            for i in range(1, steps + 1):
                frac = i / steps
                progress(
                    "Downloading...",
                    frac * 0.5,
                    f"Downloading {packages[0]}... ({i}/{steps})",
                    False,
                )
                time.sleep(0.15)
            for i in range(1, steps + 1):
                frac = 0.5 + i / steps * 0.4
                progress(
                    "Installing...",
                    frac,
                    f"Installing {packages[0]}... ({i}/{steps})",
                    False,
                )
                time.sleep(0.15)
            # Remove installed packages from every domain's update list.
            for state in self._state.values():
                state.updates[:] = [
                    u for u in state.updates if u.name not in packages
                ]
            progress(
                "Update complete",
                1.0,
                "Done. Exit (►) to restart pi-Stomp.",
                True,
            )

        progress(
            "Downloading...",
            0.0,
            f"Downloading {len(packages)} package(s)...",
            False,
        )
        threading.Thread(target=step, args=(4,), daemon=True).start()
        return True


class EmulatorServiceBackend(ServiceBackend):
    """Stub system integration for the emulator."""

    def __init__(self, boot_mode: BootMode = BootMode.USER_RECOVERY) -> None:
        self._boot_mode: BootMode = boot_mode

    def stop_main_app(self) -> bool:
        return True

    def start_main_app(self) -> bool:
        logger.info("Resuming main app (emulated)")
        return True

    def restart_jack(self) -> bool:
        logger.info("Restarting JACK (emulated)")
        return True

    def restart_mod(self) -> bool:
        logger.info("Restarting MOD (emulated)")
        return True

    def reboot(self) -> None:
        logger.info("Reboot (emulated)")

    def power_off(self) -> None:
        logger.info("Power off (emulated)")

    def recovery_sha(self) -> str:
        return "0a1b2c3"

    def crash_info(self) -> CrashInfo | None:
        if self._boot_mode != BootMode.CRASH_RECOVERY:
            return None
        return CrashInfo(
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
