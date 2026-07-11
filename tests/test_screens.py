# pyright: reportPrivateUsage=false
"""Integration tests that drive the recovery app via fake backends.

Each test asserts behavior (navigation, confirm, progress) and captures
snapshots of the rendered frame at key transitions to catch visual
regressions. Run with --snapshot-update to regenerate snapshots.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import pytest

from pistomp_recovery.app import RecoveryAppCore
from pistomp_recovery.backends import AppBackends
from pistomp_recovery.items import Action, Item, PackageUpdate, Row, Target
from pistomp_recovery.service import BootMode, CrashInfo
from pistomp_recovery.ui.screens.menu_screen import MenuScreen
from pistomp_recovery.ui.widgets.header import ICON_BACK, ICON_EXIT
from pistomp_recovery.ui.widgets.misc import InputEvent
from tests.conftest import (
    AppHarness,
    FakeDataBackend,
    FakeDisplayBackend,
    FakeInputBackend,
    FakeServiceBackend,
)


def test_badge() -> None:
    assert RecoveryAppCore.badge("updates", 2) == "2 available"
    assert RecoveryAppCore.badge("updates", 0) == ""
    assert RecoveryAppCore.badge("checkpoint", 3) == "3 available"
    assert RecoveryAppCore.badge("checkpoint", 0) == ""


def test_domain_screen_refreshes_after_successful_action(
    recovery_app: AppHarness,
    fake_data: FakeDataBackend,
) -> None:
    """After a successful action the current domain list is rebuilt from fresh data."""
    harness = recovery_app
    # Keep the main menu on the stack so pop returns somewhere sensible.
    harness.app._screen_stack[:] = [harness.app._screen_stack[0]]

    first = PackageUpdate("a", "0.1", "0.2")
    fake_data.set_updates("system", [first])
    fake_data._install_progress = [
        ("Update complete", 1.0, "Done.", True),
    ]
    harness.app._show_domain("updates", "system")
    harness.inject()
    assert harness.row_labels() == ["a 0.1"]

    # Click the update item → detail screen (async load), then install + confirm.
    harness.select("a 0.1")
    harness.drain()  # wait for package_detail loading thread

    harness.select("Install")
    harness.inject(InputEvent.RIGHT, InputEvent.CLICK)  # Yes → confirm
    harness.inject(InputEvent.CLICK)  # dismiss the done screen

    # Dismissing the done screen should re-query the domain. Because the
    # domain is now empty, the app pops back to the menu below it.
    assert fake_data._installed == [["a"]]  # type: ignore[attr-defined]
    assert harness.row_labels() == [
        "Restart Jack",
        "Restart MOD",
        "Updates",
        "Reset to Checkpoint",
        "Factory Reset",
        "Reboot",
        "Power Off",
    ]


def test_package_detail_text_rows_are_selectable(
    recovery_app: AppHarness,
    fake_data: FakeDataBackend,
    snapshot: Callable[..., None],
) -> None:
    """Text-only rows in the package detail screen are navigable for scrolling."""
    harness = recovery_app
    harness.app._screen_stack[:] = [harness.app._screen_stack[0]]

    fake_data.set_updates("system", [PackageUpdate("foo", "1.0", "2.0")])
    fake_data._package_detail_text = [
        "This is a long package description that should wrap across multiple lines on the display.",
        "",
        "Changelog:",
        "- Fixed a critical bug that caused the audio engine to crash under certain conditions",
        "- Improved latency under heavy load by up to 40 percent in real-world testing",
        "- Added support for the new hardware revision with expanded memory mapping",
    ]
    harness.app._show_domain("updates", "system")
    harness.inject()
    harness.select("foo 1.0")
    harness.drain()

    # Snapshot: detail screen with selectable text rows, selection on Install.
    snapshot("package_detail_install_focused")

    # Navigate down through text rows to verify scrolling works.
    for _ in range(6):
        harness.inject(InputEvent.RIGHT)

    snapshot("package_detail_scrolled")

    # Navigate to the Install button at the bottom.
    harness.scroll_to("Install")
    snapshot("package_detail_install")

    # Navigate back up to a long line and exercise horizontal scroll.
    # First go to the header, then step down to the first text row.
    harness.inject(InputEvent.LEFT)
    for _ in range(3):
        harness.inject(InputEvent.RIGHT)
    snapshot("package_detail_hscroll_start")
    harness.inject(InputEvent.TWEAK1_RIGHT)
    harness.inject(InputEvent.TWEAK1_RIGHT)
    snapshot("package_detail_hscroll_mid")
    harness.inject(InputEvent.TWEAK2_LEFT)
    snapshot("package_detail_hscroll_back")


def _push(harness: AppHarness, title: str, rows: list[Row], back: bool) -> MenuScreen:
    icon = Target(ICON_BACK if back else ICON_EXIT, harness.app.pop_screen)
    screen = MenuScreen(harness.app.surface, title, rows, icon)
    harness.app.push_screen(screen)
    return screen


def test_main_menu_renders(recovery_app: AppHarness, snapshot: Callable[..., None]) -> None:
    """The root menu shows the inverted title, exit icon, and top-level rows."""
    harness = recovery_app
    harness.inject()
    snapshot()

    labels = harness.nav_labels()
    assert labels[0] == ICON_EXIT  # header icon is exit on the root menu
    assert "Restart Jack" in labels and "Restart MOD" in labels
    assert "Reset to Checkpoint" in labels
    assert "Reboot" in labels and "Power Off" in labels


def test_submenu_has_back_icon(recovery_app: AppHarness, snapshot: Callable[..., None]) -> None:
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


def test_confirm_cancel(recovery_app: AppHarness, snapshot: Callable[..., None]) -> None:
    harness = recovery_app
    called: list[bool] = []
    harness.app._screen_stack.clear()
    screen = _push(
        harness,
        "Factory Reset",
        [Row((Target("jackdrc", lambda: called.append(True), confirm="Reset jackdrc?"),))],
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


def test_confirm_confirm(recovery_app: AppHarness, snapshot: Callable[..., None]) -> None:
    harness = recovery_app
    called: list[bool] = []
    harness.app._screen_stack.clear()
    screen = _push(
        harness,
        "Factory Reset",
        [Row((Target("jackdrc", lambda: called.append(True), confirm="Reset jackdrc?"),))],
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


def test_update_picker_shows_only_system(
    recovery_app: AppHarness, snapshot: Callable[..., None]
) -> None:
    """The Updates picker shows only System (the only domain with installable updates)."""
    harness = recovery_app
    harness.app._screen_stack.clear()
    fake_data = harness.app._backends.data
    assert isinstance(fake_data, FakeDataBackend)

    # Set up real package updates so the picker shows a badge.
    fake_data.set_updates(
        "system",
        [PackageUpdate("a", "0.1", "0.2"), PackageUpdate("b", "0.3", "0.4")],
    )

    harness.app._show_domain_picker("updates")
    harness.inject()
    snapshot("picker")

    menu = harness._menu()
    assert menu is not None
    # Only System appears in Updates; pedalboards/plugins/config are omitted.
    labels = harness.row_labels()
    assert labels == ["System"]
    assert menu._rows[0].right == "2 available"

    # Domain detail rows still render all items, including Update All.
    items = [
        Item("a", "a 0.1", False, "\u21910.2", [Action("Update", lambda: None)]),
        Item("b", "b 0.3", False, "\u21910.4", [Action("Update", lambda: None)]),
        Item("all", "Update All", False, "", [Action("Update All", lambda: None)]),
    ]
    _push(
        harness,
        "System",
        [Row((Target(it.label, lambda: None),), right=it.right) for it in items],
        back=True,
    )
    harness.inject()
    snapshot("domain_list")
    assert harness.row_labels() == ["a 0.1", "b 0.3", "Update All"]


def test_plugin_facet_cache_summary(tmp_path: Path) -> None:
    """PluginFacet.cache_summary returns a human-readable size badge."""
    from pistomp_recovery.plugins import PluginFacet

    facet = PluginFacet(path=tmp_path)
    assert facet.cache_summary() == ""

    bundle = tmp_path / "some-amp.lv2"
    bundle.mkdir()
    (bundle / "patchstorage.json").write_text("{}")
    (bundle / "amp.so").write_bytes(b"\x00" * 1024)

    summary = facet.cache_summary()
    assert "1" in summary or "KB" in summary
    assert "⚠" not in summary


def test_plugin_facet_list_items(tmp_path: Path) -> None:
    """PluginFacet.list_items returns user bundles with factory-reset actions."""
    from pistomp_recovery.plugins import PluginFacet

    facet = PluginFacet(path=tmp_path)

    # No bundles → empty list.
    assert facet.list_items() == []

    # Create a user-installed bundle (has patchstorage.json marker).
    bundle = tmp_path / "some-amp.lv2"
    bundle.mkdir()
    (bundle / "patchstorage.json").write_text("{}")
    (bundle / "amp.so").write_bytes(b"\x00" * 1024)

    items = facet.list_items()
    assert len(items) == 1
    assert items[0].name == "some-amp.lv2"
    assert items[0].dirty
    assert any(a.label == "Rollback to factory" for a in items[0].actions)

    # Bundle without marker is ignored.
    (tmp_path / "factory-only.lv2").mkdir()
    (tmp_path / "factory-only.lv2" / "factory.so").write_bytes(b"\x00" * 64)
    assert len(facet.list_items()) == 1


def test_update_items_are_selectable_with_empty_actions(
    recovery_app: AppHarness,
) -> None:
    """Update items with no actions must still be selectable (not disabled)."""
    harness = recovery_app
    harness.app._screen_stack.clear()
    fake_data = harness.app._backends.data
    assert isinstance(fake_data, FakeDataBackend)
    fake_data.set_updates(
        "system",
        [PackageUpdate("a", "0.1", "0.2"), PackageUpdate("b", "0.3", "0.4")],
    )
    harness.app._show_domain("updates", "system")
    harness.inject()

    menu = harness._menu()
    assert menu is not None
    assert harness.row_labels() == ["a 0.1", "b 0.3", "Update All"]
    # All update items should be navigable (enabled) even with empty actions.
    assert all(target.enabled for row in menu._rows for target in row.targets)


def test_expanded_pi_stomp_selecting_directly_shows_info(
    recovery_app: AppHarness,
    fake_data: FakeDataBackend,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    snapshot: Callable[..., None],
) -> None:
    """When pi-stomp's git tree is expanded, the row shows the local hash
    + dirty marker instead of the apt version, and selecting it pops an
    OK-only info dialog explaining why the update cannot proceed.
    """
    marker = tmp_path / "EXPANDED"
    marker.write_text("")
    monkeypatch.setattr("pistomp_recovery.app.PISTOMP_EXPANDED_MARKER", str(marker))
    monkeypatch.setattr(
        "pistomp_recovery.app.git_util.local_status",
        lambda _path: ("b66fdff1", True),
    )

    fake_data.set_updates(
        "system",
        [
            PackageUpdate("pi-stomp", "1.0", "1.1"),
            PackageUpdate("a", "0.1", "0.2"),
        ],
    )

    harness = recovery_app
    harness.app._show_domain("updates", "system")
    harness.inject()
    snapshot("domain_list")

    menu = harness._menu()
    assert menu is not None
    assert harness.row_labels() == ["pi-stomp b66fdff1*", "a 0.1", "Update All"]

    # LEFT/RIGHT are no-ops on the info dialog (no second button to focus).
    harness.scroll_to("pi-stomp b66fdff1*")
    harness.inject(InputEvent.LEFT, InputEvent.RIGHT)
    assert menu._state == "LIST"

    harness.select("pi-stomp b66fdff1*")
    snapshot("info_dialog")

    assert menu._state == "CONFIRM"
    assert menu._confirm_dialog is not None
    assert "Cannot update pi-stomp" in menu._confirm_dialog._title
    assert "contract-git.sh" in menu._confirm_dialog._title
    # No second button: the info dialog has on_cancel=None.
    assert menu._confirm_dialog._on_cancel is None

    # LEFT/RIGHT are no-ops — only CLICK dismisses the info dialog.
    harness.inject(InputEvent.LEFT, InputEvent.RIGHT)
    assert menu._state == "CONFIRM"

    # OK dismisses the dialog and is a no-op; the backend is never asked to install.
    harness.inject(InputEvent.CLICK)
    assert menu._state == "LIST"
    assert fake_data._installed == []


def test_expanded_pi_stomp_clean_label_omits_marker(
    recovery_app: AppHarness,
    fake_data: FakeDataBackend,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A clean working tree shows just the short hash (no trailing '*')."""
    marker = tmp_path / "EXPANDED"
    marker.write_text("")
    monkeypatch.setattr("pistomp_recovery.app.PISTOMP_EXPANDED_MARKER", str(marker))
    monkeypatch.setattr(
        "pistomp_recovery.app.git_util.local_status",
        lambda _path: ("a1b2c3d", False),
    )

    fake_data.set_updates(
        "system",
        [PackageUpdate("pi-stomp", "1.0", "1.1")],
    )

    harness = recovery_app
    harness.app._show_domain("updates", "system")
    harness.inject()
    assert harness.row_labels()[0] == "pi-stomp a1b2c3d"


def test_expanded_pi_stomp_skipped_from_update_all(
    recovery_app: AppHarness,
    fake_data: FakeDataBackend,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    snapshot: Callable[..., None],
) -> None:
    """When pi-stomp's git tree is expanded, 'Update All' filters pi-stomp
    out of the install list and surfaces a note in the confirm dialog.
    """
    marker = tmp_path / "EXPANDED"
    marker.write_text("")
    monkeypatch.setattr("pistomp_recovery.app.PISTOMP_EXPANDED_MARKER", str(marker))
    monkeypatch.setattr(
        "pistomp_recovery.app.git_util.local_status",
        lambda _path: ("b66fdff1", True),
    )

    fake_data.set_updates(
        "system",
        [
            PackageUpdate("pi-stomp", "1.0", "1.1"),
            PackageUpdate("a", "0.1", "0.2"),
        ],
    )
    fake_data._install_progress = [
        ("Update complete", 1.0, "Done.", True),
    ]

    harness = recovery_app
    harness.app._show_domain("updates", "system")
    harness.inject()

    # "Update All" badge reflects the actual install count (pi-stomp filtered).
    domain = harness.app._screen_stack[-1]  # type: ignore[attr-defined]
    all_row = next(r for r in domain._rows if r.targets[0].label == "Update All")
    assert all_row.right == "1 pkgs"

    # The pi-stomp row is flagged in the error color to indicate the upgrade
    # is blocked.
    pi_row = next(r for r in domain._rows if "pi-stomp" in r.targets[0].label)
    assert pi_row.right_color == "error"

    harness.select("Update All")
    menu = harness._menu()
    assert menu is not None
    assert menu._state == "CONFIRM"
    assert menu._confirm_dialog is not None
    # Confirm message advertises that pi-stomp will be skipped.
    assert "pi-stomp skipped" in menu._confirm_dialog._title
    assert "using git" in menu._confirm_dialog._title
    assert "1 package" in menu._confirm_dialog._title
    snapshot("update_all_confirm")

    # Confirm: only the non-pi-stomp package should be installed.
    harness.inject(InputEvent.RIGHT, InputEvent.CLICK)
    assert fake_data._installed == [["a"]]


def test_plugins_factory_picker_shows_count_badge(
    recovery_app: AppHarness, snapshot: Callable[..., None]
) -> None:
    """Factory Reset → Plugins shows the factory plugin count badge from domain_summary."""
    harness = recovery_app
    harness.app._screen_stack.clear()
    fake_data = harness.app._backends.data
    assert isinstance(fake_data, FakeDataBackend)

    # 12 plugins: 8 stamped, 2 unstamped+dirty, 2 factory.
    plugins: list[Item] = [
        Item(
            "stamped-amp.lv2",
            "stamped-amp.lv2",
            False,
            "2d ago",
            [Action("Rollback to factory", lambda: None)],
        ),
        Item(
            "stamped-delay.lv2",
            "stamped-delay.lv2",
            False,
            "5h ago",
            [Action("Rollback to factory", lambda: None)],
        ),
        Item(
            "stamped-reverb.lv2",
            "stamped-reverb.lv2",
            False,
            "1d ago",
            [Action("Rollback to factory", lambda: None)],
        ),
        Item(
            "stamped-chorus.lv2",
            "stamped-chorus.lv2",
            False,
            "3d ago",
            [Action("Rollback to factory", lambda: None)],
        ),
        Item(
            "stamped-flanger.lv2",
            "stamped-flanger.lv2",
            False,
            "6h ago",
            [Action("Rollback to factory", lambda: None)],
        ),
        Item(
            "stamped-comp.lv2",
            "stamped-comp.lv2",
            False,
            "just now",
            [Action("Rollback to factory", lambda: None)],
        ),
        Item(
            "stamped-eq.lv2",
            "stamped-eq.lv2",
            False,
            "2h ago",
            [Action("Rollback to factory", lambda: None)],
        ),
        Item(
            "stamped-dist.lv2",
            "stamped-dist.lv2",
            False,
            "4d ago",
            [Action("Rollback to factory", lambda: None)],
        ),
        Item(
            "dirty-trem.lv2",
            "dirty-trem.lv2",
            True,
            "12 KB",
            [Action("Rollback to factory", lambda: None)],
        ),
        Item(
            "dirty-wah.lv2",
            "dirty-wah.lv2",
            True,
            "8 KB",
            [Action("Rollback to factory", lambda: None)],
        ),
        Item(
            "factory-tuner.lv2",
            "factory-tuner.lv2",
            False,
            "factory",
            [Action("Rollback to factory", lambda: None)],
        ),
        Item(
            "factory-noise.lv2",
            "factory-noise.lv2",
            False,
            "factory",
            [Action("Rollback to factory", lambda: None)],
        ),
    ]
    fake_data.set_items("factory", "plugins", plugins)
    fake_data.set_domain_summary("factory", "plugins", "517")

    harness.app._show_domain_picker("factory")
    harness.inject()
    snapshot("picker")

    menu = harness._menu()
    assert menu is not None
    assert menu._rows[1].right == "517"  # factory plugin count badge

    # Navigate into plugins → should open factory restore menu, not plugin list.
    harness.select("Plugins")
    snapshot("plugins_list")

    labels = harness.row_labels()
    assert labels == ["Reset all factory plugins"]


def test_picker_badge_refreshes_after_domain_action(
    recovery_app: AppHarness,
) -> None:
    """After a 3rd-level domain action the 2nd-level picker badges update."""
    harness = recovery_app
    harness.inject()

    # Set up one dirty pedalboard so the picker shows a badge.
    fake_data = harness.app._backends.data
    assert isinstance(fake_data, FakeDataBackend)

    def clear_pedalboards() -> None:
        fake_data.set_items("checkpoint", "pedalboards", [])

    dirty = Item(
        "dirty.pedalboard",
        "dirty.pedalboard",
        True,
        "2d ago",
        [Action("Rollback to stamp", clear_pedalboards)],
    )
    fake_data.set_items("checkpoint", "pedalboards", [dirty])

    harness.select("Reset to Checkpoint")
    picker = harness._menu()
    assert picker is not None
    assert picker._rows[0].right == "1 available"

    harness.select("Pedalboards")
    harness.select("dirty.pedalboard")

    # The wrapped action cleared the domain and the domain was popped; the
    # picker badge should now reflect the new (empty) state.
    assert picker._rows[0].right == ""


def test_reset_picker_navigation(recovery_app: AppHarness) -> None:
    """RESET TO CHECKPOINT drills into the shared domain picker."""
    harness = recovery_app
    harness.inject()
    harness.select("Reset to Checkpoint")

    labels = harness.row_labels()
    assert labels == ["Pedalboards", "Plugins", "Config", "System"]

    # Plugins is selectable but leads to an empty list.
    harness.select("Plugins")
    assert harness.row_labels() == ["No updates"] or harness.row_labels() == ["Nothing to reset"]


def test_crash_recovery_boot(
    fake_display: FakeDisplayBackend,
    fake_input: FakeInputBackend,
    fake_data: FakeDataBackend,
) -> None:
    """Booting in crash mode shows the crash screen."""
    services = FakeServiceBackend(boot_mode=BootMode.CRASH_RECOVERY)
    app = RecoveryAppCore(
        AppBackends(
            display=fake_display,
            input=fake_input,
            data=fake_data,
            services=services,
        ),
        CrashInfo(
            boot_mode=BootMode.CRASH_RECOVERY,
            failed_service=None,
            crash_log="",
            crash_log_full="",
            service_states={},
        ),
    )
    app.init()
    screen = app.current_screen()
    from pistomp_recovery.ui.screens.crash import CrashScreen

    assert isinstance(screen, CrashScreen)
    app.cleanup()


def test_crash_screen_snapshot(
    fake_display: FakeDisplayBackend,
    fake_input: FakeInputBackend,
    fake_data: FakeDataBackend,
    snapshot: Callable[..., None],
) -> None:
    """CrashScreen renders service states, log tail, and RESUME | RECOVERY actions."""
    crash_info = CrashInfo(
        boot_mode=BootMode.CRASH_RECOVERY,
        failed_service="jack",
        crash_log=(
            "ALSA lib pcm.c:2664: Unknown PCM cards.pcm.front\n"
            "jackd: Failed to initialize backend\n"
            "jack: server is not running or cannot be started"
        ),
        crash_log_full=(
            "ALSA lib pcm.c:2664: Unknown PCM cards.pcm.front\n"
            "jackd: Failed to initialize backend\n"
            "jack: server is not running or cannot be started"
        ),
        service_states={
            "jack": "failed",
            "mod-host": "inactive",
            "mod-ui": "inactive",
            "mod-ala-pi-stomp": "inactive",
        },
        service_results={
            "jack": "exit-code",
            "mod-host": "success",
            "mod-ui": "success",
            "mod-ala-pi-stomp": "success",
        },
    )
    services = FakeServiceBackend(
        boot_mode=BootMode.CRASH_RECOVERY,
        crash_info_override=crash_info,
    )
    app = RecoveryAppCore(
        AppBackends(
            display=fake_display,
            input=fake_input,
            data=fake_data,
            services=services,
        ),
        crash_info,
    )
    app.init()
    harness = AppHarness(app, fake_display)
    harness.inject()
    snapshot("resume_focused")

    harness.inject(InputEvent.RIGHT)
    snapshot("recovery_focused")

    app.cleanup()


def test_crash_screen_reports_missing_log(
    fake_display: FakeDisplayBackend,
    fake_input: FakeInputBackend,
    fake_data: FakeDataBackend,
) -> None:
    """A crash whose journal read failed must say so, not render a blank panel."""
    from pistomp_recovery.ui.screens.crash import NO_LOG_MESSAGE, CrashScreen

    crash_info = CrashInfo(
        boot_mode=BootMode.CRASH_RECOVERY,
        failed_service="jack",
        crash_log="",
        crash_log_full="",
        service_states={"jack": "failed"},
        service_results={"jack": "exit-code"},
    )
    app = RecoveryAppCore(
        AppBackends(
            display=fake_display,
            input=fake_input,
            data=fake_data,
            services=FakeServiceBackend(
                boot_mode=BootMode.CRASH_RECOVERY,
                crash_info_override=crash_info,
            ),
        ),
        crash_info,
    )
    app.init()
    screen = app.current_screen()
    assert isinstance(screen, CrashScreen)

    assert NO_LOG_MESSAGE in [row.prefix for row in screen._rows]

    app.cleanup()


def test_crash_screen_no_missing_log_message_without_failed_service(
    fake_display: FakeDisplayBackend,
) -> None:
    """No failed service means there is no log to miss — stay quiet."""
    from pistomp_recovery.ui.screens.crash import NO_LOG_MESSAGE, CrashScreen

    def _noop() -> None:
        return None

    screen = CrashScreen(
        fake_display.surface,
        on_resume=_noop,
        on_recovery=_noop,
        on_show_log=_noop,
        crash_info=CrashInfo(
            boot_mode=BootMode.USER_RECOVERY,
            failed_service=None,
            crash_log="",
            crash_log_full="",
            service_states={"jack": "active"},
        ),
    )

    assert NO_LOG_MESSAGE not in [row.prefix for row in screen._rows]


def test_resume_starts_main_app(
    fake_display: FakeDisplayBackend,
    fake_input: FakeInputBackend,
    fake_data: FakeDataBackend,
) -> None:
    """Selecting exit on the root menu starts the main app and stops the loop."""
    services = FakeServiceBackend()
    app = RecoveryAppCore(
        AppBackends(
            display=fake_display,
            input=fake_input,
            data=fake_data,
            services=services,
        ),
        CrashInfo(
            boot_mode=BootMode.USER_RECOVERY,
            failed_service=None,
            crash_log="",
            crash_log_full="",
            service_states={},
        ),
    )
    app.init()
    # Navigate to the exit icon (header target) and select it.
    app.handle_event(InputEvent.LEFT)
    app.handle_event(InputEvent.CLICK)
    assert "start_main_app" in services.calls
    assert not app.running
    app.cleanup()


def _wait_for_restart(harness: AppHarness) -> None:
    """Block until the restart worker thread completes and the UI is dirty."""
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        time.sleep(0.01)
        if harness.app._lcd_needs_update:
            harness.redraw()
            return
    raise TimeoutError("Restart worker did not complete in time")


def test_restart_jack_success(
    recovery_app: AppHarness,
    fake_services: FakeServiceBackend,
    snapshot: Callable[..., None],
) -> None:
    """Clicking Jack shows progress, then a done message when the service comes up."""
    harness = recovery_app
    harness.inject()

    harness.select("Restart Jack")

    # Wait for the restart thread to finish (fake backend is instant).
    _wait_for_restart(harness)

    assert "restart_jack" in fake_services.calls
    assert any("diagnose_services:jack" in c for c in fake_services.calls)

    # Thread reported success → menu is in PROGRESS done state.
    menu = harness._menu()
    assert menu is not None
    assert menu._state == "PROGRESS"
    assert menu._progress_done
    snapshot("done")

    # Click to dismiss → back to the list.
    harness.inject(InputEvent.CLICK)
    assert menu._state == "LIST"


def test_restart_jack_failure(
    fake_display: FakeDisplayBackend,
    fake_input: FakeInputBackend,
    fake_data: FakeDataBackend,
    snapshot: Callable[..., None],
) -> None:
    """When Jack fails to restart, a result screen with service states is shown."""
    failing_diagnosis = CrashInfo(
        boot_mode=BootMode.CRASH_RECOVERY,
        failed_service="jack",
        crash_log="ALSA: cannot find card\nJACK: server failed",
        crash_log_full="ALSA: cannot find card\nJACK: server failed",
        service_states={"jack": "failed"},
    )
    services = FakeServiceBackend(restart_diagnosis=failing_diagnosis)
    app = RecoveryAppCore(
        AppBackends(
            display=fake_display,
            input=fake_input,
            data=fake_data,
            services=services,
        ),
        CrashInfo(
            boot_mode=BootMode.USER_RECOVERY,
            failed_service=None,
            crash_log="",
            crash_log_full="",
            service_states={},
        ),
    )
    app.init()
    harness = AppHarness(app, fake_display)
    harness.inject()

    harness.select("Restart Jack")

    # Wait for thread to push the failure screen.
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and len(app._screen_stack) < 2:
        time.sleep(0.01)
    harness.redraw()

    # A new screen should have been pushed.
    assert len(app._screen_stack) == 2
    result_screen = app.current_screen()
    assert isinstance(result_screen, MenuScreen)
    assert "Jack" in result_screen._title
    assert "Failed" in result_screen._title
    snapshot("failure_screen")

    # The result screen shows BACK and RETRY actions.
    labels = harness.nav_labels()
    assert "BACK" in labels
    assert "RETRY" in labels

    # BACK pops back to the main menu.
    harness.select("BACK")
    assert len(app._screen_stack) == 1
    snapshot("after_back")

    app.cleanup()
