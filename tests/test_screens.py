"""Integration and snapshot tests for new screens."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pygame
import pytest

from pistomp_recovery.constants import LCD_HEIGHT, LCD_WIDTH
from pistomp_recovery.facets.packages_facet import PackageItem
from pistomp_recovery.facets.pedalboards_facet import PedalboardItem
from pistomp_recovery.ui.colors import COLORS
from pistomp_recovery.ui.screens.main_menu import MainMenuScreen
from pistomp_recovery.ui.screens.packages_screen import PackagesScreen
from pistomp_recovery.ui.screens.pedalboards_screen import PedalboardsScreen
from pistomp_recovery.ui.screens.reset_screen import DirtyItem, ResetScreen
from pistomp_recovery.ui.screens.types import Actions
from pistomp_recovery.ui.screens.updates import UpdatesScreen
from pistomp_recovery.ui.widgets.confirm_dialog import ConfirmDialog
from pistomp_recovery.ui.widgets.misc import InputEvent
from tests.conftest import FakeLcd


@pytest.fixture
def surface() -> pygame.Surface:
    return pygame.Surface((LCD_WIDTH, LCD_HEIGHT))


class TestMainMenuScreen:
    def test_menu_with_badges(
        self, surface: pygame.Surface, fake_lcd: FakeLcd, snapshot: Callable[..., None]
    ) -> None:
        actions: Actions = {
            "resume": lambda: None,
            "reset": lambda: None,
            "update": lambda: None,
            "pedalboards": lambda: None,
            "packages": lambda: None,
            "system_info": lambda: None,
            "reboot": lambda: None,
            "power_off": lambda: None,
        }
        menu: MainMenuScreen = MainMenuScreen(
            surface,
            actions=actions,
            dirty_count=3,
            update_count=2,
        )
        menu.draw()
        fake_lcd.update(surface)
        snapshot()

    def test_menu_no_badges(
        self, surface: pygame.Surface, fake_lcd: FakeLcd, snapshot: Callable[..., None]
    ) -> None:
        actions: Actions = {
            "resume": lambda: None,
            "reset": lambda: None,
            "update": lambda: None,
            "pedalboards": lambda: None,
            "packages": lambda: None,
            "system_info": lambda: None,
            "reboot": lambda: None,
            "power_off": lambda: None,
        }
        menu: MainMenuScreen = MainMenuScreen(
            surface,
            actions=actions,
            dirty_count=0,
            update_count=0,
        )
        menu.draw()
        fake_lcd.update(surface)
        snapshot()


class TestPedalboardsScreen:
    def test_pedalboard_list(
        self, surface: pygame.Surface, fake_lcd: FakeLcd, snapshot: Callable[..., None]
    ) -> None:
        items: list[PedalboardItem] = [
            PedalboardItem(
                name="AmpBud.pedalboard",
                path=Path("/tmp/AmpBud.pedalboard"),
                is_dirty=True,
                last_stamp_time=datetime(2026, 6, 9, 10, 0, tzinfo=timezone.utc),
                last_stamp_tag="stamp/pedalboard/AmpBud.pedalboard/20260609-100000",
            ),
            PedalboardItem(
                name="Beths.pedalboard",
                path=Path("/tmp/Beths.pedalboard"),
                is_dirty=False,
                last_stamp_time=datetime(2026, 6, 8, 14, 30, tzinfo=timezone.utc),
                last_stamp_tag="stamp/pedalboard/Beths.pedalboard/20260608-143000",
            ),
            PedalboardItem(
                name="factory-defaults.pedalboard",
                path=Path("/tmp/factory-defaults.pedalboard"),
                is_dirty=False,
                last_stamp_time=None,
                last_stamp_tag=None,
            ),
        ]
        screen: PedalboardsScreen = PedalboardsScreen(
            surface,
            items,
            on_stamp=lambda n: None,
            on_rollback_stamp=lambda n: None,
            on_rollback_factory=lambda n: None,
        )
        screen.draw()
        fake_lcd.update(surface)
        snapshot()


class TestPackagesScreen:
    def test_package_list(
        self, surface: pygame.Surface, fake_lcd: FakeLcd, snapshot: Callable[..., None]
    ) -> None:
        items: list[PackageItem] = [
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
        screen: PackagesScreen = PackagesScreen(
            surface,
            items,
            pending_restart=["jack"],
            on_stamp=lambda n: None,
            on_rollback_stamp=lambda n: None,
            on_rollback_factory=lambda n: None,
            on_update=lambda n: None,
            on_restart_services=lambda: None,
        )
        screen.draw()
        fake_lcd.update(surface)
        snapshot()


class TestUpdateScreen:
    def test_updates_available(
        self, surface: pygame.Surface, fake_lcd: FakeLcd, snapshot: Callable[..., None]
    ) -> None:
        screen: UpdatesScreen = UpdatesScreen(
            surface,
            [("jack2-pistomp", "1.9.12", "1.9.13"), ("mod-ui", "0.13.0", "0.14.0")],
            on_install=lambda pkgs: None,
            on_install_single=lambda pkg: None,
        )
        screen.draw()
        fake_lcd.update(surface)
        snapshot()

    def test_no_updates(
        self, surface: pygame.Surface, fake_lcd: FakeLcd, snapshot: Callable[..., None]
    ) -> None:
        screen: UpdatesScreen = UpdatesScreen(
            surface,
            [],
            on_install=lambda pkgs: None,
            on_install_single=lambda pkg: None,
        )
        screen.draw()
        fake_lcd.update(surface)
        snapshot()


class TestConfirmDialog:
    def test_confirm_dialog(
        self, surface: pygame.Surface, fake_lcd: FakeLcd, snapshot: Callable[..., None]
    ) -> None:
        surface.fill(COLORS["bg"])
        dialog: ConfirmDialog = ConfirmDialog(
            surface, "Factory reset\nall data?", lambda: None, lambda: None
        )
        dialog.draw()
        fake_lcd.update(surface)
        snapshot()

    def test_confirm_dialog_selected(
        self, surface: pygame.Surface, fake_lcd: FakeLcd, snapshot: Callable[..., None]
    ) -> None:
        surface.fill(COLORS["bg"])
        dialog: ConfirmDialog = ConfirmDialog(
            surface, "Factory reset\nall data?", lambda: None, lambda: None
        )
        dialog.handle_event(InputEvent.RIGHT)
        dialog.draw()
        fake_lcd.update(surface)
        snapshot("selected")


class TestResetScreen:
    def test_reset_dirty_items(
        self, surface: pygame.Surface, fake_lcd: FakeLcd, snapshot: Callable[..., None]
    ) -> None:
        items: list[DirtyItem] = [
            DirtyItem(
                label="\u25cf AmpBud.pedalboard",
                right="3h ago",
                kind="pedalboard",
                name="AmpBud.pedalboard",
            ),
            DirtyItem(
                label="\u25cf jack2-pistomp",
                right="1.9.12 \u2192 1.9.11  yesterday",
                kind="package",
                name="jack2-pistomp",
            ),
        ]
        screen: ResetScreen = ResetScreen(
            surface,
            items,
            on_rollback_stamp=lambda k, n: None,
            on_rollback_factory=lambda k, n: None,
        )
        screen.draw()
        fake_lcd.update(surface)
        snapshot()
