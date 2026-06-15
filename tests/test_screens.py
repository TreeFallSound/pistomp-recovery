"""Integration tests that drive the real RecoveryApp via fake hardware.

Each test asserts behavior (navigation, confirm, progress) and captures
snapshots of the rendered frame at key transitions to catch visual
regressions. Run with --snapshot-update to regenerate snapshots.
"""

from __future__ import annotations

from typing import Callable

from pistomp_recovery.items import Row, Target
from pistomp_recovery.ui.screens.menu_screen import MenuScreen
from pistomp_recovery.ui.widgets.header import ICON_BACK, ICON_EXIT
from pistomp_recovery.ui.widgets.misc import InputEvent
from tests.conftest import AppHarness


def _push(harness: AppHarness, title: str, rows: list[Row], back: bool) -> MenuScreen:
    icon = Target(ICON_BACK if back else ICON_EXIT, harness.app._pop_screen)
    screen = MenuScreen(harness.surface, title, rows, icon)
    harness.app._push_screen(screen)
    return screen


def test_main_menu_renders(
    recovery_app: AppHarness, snapshot: Callable[..., None]
) -> None:
    """The root menu shows the inverted title, exit icon, and top-level rows."""
    harness = recovery_app
    harness.inject()
    snapshot()

    labels = harness.nav_labels()
    assert labels[0] == ICON_EXIT  # header icon is exit on the root menu
    assert "JACK" in labels and "MOD" in labels
    assert "RESET TO CHECKPOINT" in labels
    assert "REBOOT" in labels and "POWER OFF" in labels


def test_submenu_has_back_icon(
    recovery_app: AppHarness, snapshot: Callable[..., None]
) -> None:
    """Sub-screens carry a back icon in the header instead of an exit icon."""
    harness = recovery_app
    harness.app._screen_stack.clear()
    _push(
        harness,
        "Pedalboards",
        [Row((Target("foo.pedalboard", lambda: None, enabled=False),), right="factory")],
        back=True,
    )
    harness.inject()
    snapshot()

    assert harness.nav_labels()[0] == ICON_BACK


def test_disabled_target_skipped(recovery_app: AppHarness) -> None:
    """Disabled targets render but are not reachable by the encoder."""
    harness = recovery_app
    harness.app._screen_stack.clear()
    _push(
        harness,
        "Plugins",
        [Row((Target("No updates", lambda: None, enabled=False),))],
        back=True,
    )
    harness.inject()
    # Only the header icon is navigable.
    assert harness.nav_labels() == [ICON_BACK]
    assert harness.row_labels() == ["No updates"]


def test_confirm_cancel(
    recovery_app: AppHarness, snapshot: Callable[..., None]
) -> None:
    harness = recovery_app
    called: list[bool] = []
    harness.app._screen_stack.clear()
    screen = _push(
        harness,
        "Factory Reset",
        [Row((Target("jackdrc", lambda: called.append(True),
                     confirm="Reset jackdrc?"),))],
        back=True,
    )
    harness.inject()
    snapshot("list")

    harness.select("jackdrc")
    assert screen._state == "CONFIRM"
    snapshot("confirm")

    harness.inject(InputEvent.CLICK)  # No is focused by default -> cancel
    assert screen._state == "LIST"
    assert called == []
    snapshot("cancelled")


def test_confirm_confirm(
    recovery_app: AppHarness, snapshot: Callable[..., None]
) -> None:
    harness = recovery_app
    called: list[bool] = []
    harness.app._screen_stack.clear()
    screen = _push(
        harness,
        "Factory Reset",
        [Row((Target("jackdrc", lambda: called.append(True),
                     confirm="Reset jackdrc?"),))],
        back=True,
    )
    harness.inject()

    harness.select("jackdrc")
    assert screen._state == "CONFIRM"
    harness.inject(InputEvent.RIGHT, InputEvent.CLICK)  # move to Yes, confirm
    assert called == [True]
    assert screen._state == "LIST"
    snapshot("confirmed")


def test_progress_blocks_then_dismisses(
    recovery_app: AppHarness, snapshot: Callable[..., None]
) -> None:
    harness = recovery_app
    harness.app._screen_stack.clear()
    screen = _push(harness, "Updates", [], back=True)

    screen.set_progress("Downloading...", 0.5, "Downloading 2 package(s)...")
    harness.inject()
    snapshot("progress")
    assert screen._state == "PROGRESS"

    # Input is blocked while in progress.
    harness.inject(InputEvent.RIGHT, InputEvent.CLICK, InputEvent.LONG_CLICK)
    assert screen._state == "PROGRESS"

    # Once marked done, a click dismisses back to the list.
    screen.set_progress("Update complete", 1.0, "Done.", done=True)
    harness.redraw()
    snapshot("done")
    harness.inject(InputEvent.CLICK)
    assert screen._state == "LIST"


def test_reset_picker_navigation(recovery_app: AppHarness) -> None:
    """RESET TO CHECKPOINT drills into the shared domain picker."""
    harness = recovery_app
    harness.inject()
    harness.select("RESET TO CHECKPOINT")

    labels = harness.row_labels()
    assert labels == ["Pedalboards", "Plugins", "Config", "System"]

    # Plugins is selectable but leads to an empty list.
    harness.select("Plugins")
    assert harness.row_labels() == ["No updates"] or harness.row_labels() == [
        "Nothing to reset"
    ]
