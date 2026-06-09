from __future__ import annotations

from typing import Callable

import pygame

from pistomp_recovery.facets.packages_facet import PackageItem
from pistomp_recovery.ui.colors import COLORS, Color
from pistomp_recovery.ui.screens import Screen
from pistomp_recovery.ui.widgets.confirm_dialog import ConfirmDialog
from pistomp_recovery.ui.widgets.menu import Menu
from pistomp_recovery.ui.widgets.misc import Box, InputEvent
from pistomp_recovery.ui.widgets.paint import PaintContext
from pistomp_recovery.ui.widgets.text import StatusLine


class PackagesScreen(Screen):
    def __init__(
        self,
        surface: pygame.Surface,
        items: list[PackageItem],
        pending_restart: list[str] | None = None,
        on_stamp: Callable[[str], None] | None = None,
        on_rollback_stamp: Callable[[str], None] | None = None,
        on_rollback_factory: Callable[[str], None] | None = None,
        on_update: Callable[[str], None] | None = None,
        on_restart_services: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(surface)
        self._items: list[PackageItem] = items
        self._on_stamp: Callable[[str], None] | None = on_stamp
        self._on_rollback_stamp: Callable[[str], None] | None = on_rollback_stamp
        self._on_rollback_factory: Callable[[str], None] | None = on_rollback_factory
        self._on_update: Callable[[str], None] | None = on_update
        self._on_restart_services: Callable[[], None] | None = on_restart_services
        self._pending_restart: list[str] = pending_restart or []
        self._menu: Menu = Menu(Box(4, 24, 312, 180), title="Packages")
        self._status: StatusLine = StatusLine(Box(4, 210, 312, 22))
        self._detail_index: int | None = None
        self._showing_confirm: bool = False
        self._confirm_action: str = ""
        self._confirm_target: str = ""
        self._build_menu()

    def _build_menu(self) -> None:
        self._menu.clear_items()
        for item in self._items:
            label: str = item.display_name
            right: str = item.display_right
            self._menu.add_item(
                label, lambda i=item: self._select_item(i), right
            )
        self._menu.add_item("\u2190 Back", self._go_back)

    def _select_item(self, item: PackageItem) -> None:
        idx: int = self._items.index(item)
        self._detail_index = idx
        self._build_detail_menu(item)

    def _build_detail_menu(self, item: PackageItem) -> None:
        self._menu.clear_items()
        self._menu.add_item(
            f"{item.name}  {item.display_version}",
            lambda: None,
        )
        if item.available_version:
            self._menu.add_item(
                f"Update to {item.available_version}",
                lambda: self._update_item(item.name),
            )
        if not item.is_dirty:
            self._menu.add_item(
                "Stamp current version",
                lambda: self._stamp_item(item.name),
            )
        if item.stamped_version and item.is_dirty:
            self._menu.add_item(
                "Rollback to stamp",
                lambda: self._start_confirm("stamp", item.name),
            )
        if item.factory_version:
            self._menu.add_item(
                "Rollback to factory",
                lambda: self._start_confirm("factory", item.name),
            )
        if self._pending_restart:
            svc_list: str = ", ".join(self._pending_restart)
            self._menu.add_item(
                f"Restart: {svc_list}", self._restart_services
            )
        self._menu.add_item("\u2190 Back", self._back_to_list)

    def _update_item(self, name: str) -> None:
        if self._on_update:
            self._on_update(name)

    def _stamp_item(self, name: str) -> None:
        if self._on_stamp:
            self._on_stamp(name)

    def _start_confirm(self, action: str, name: str) -> None:
        self._showing_confirm = True
        self._confirm_action = action
        self._confirm_target = name

    def _do_confirm(self) -> None:
        if self._confirm_action == "stamp" and self._on_rollback_stamp:
            self._on_rollback_stamp(self._confirm_target)
        elif self._confirm_action == "factory" and self._on_rollback_factory:
            self._on_rollback_factory(self._confirm_target)
        self._showing_confirm = False

    def _do_cancel(self) -> None:
        self._showing_confirm = False

    def _restart_services(self) -> None:
        if self._on_restart_services:
            self._on_restart_services()

    def _back_to_list(self) -> None:
        self._detail_index = None
        self._build_menu()

    def set_status(self, text: str, color: Color | None = None) -> None:
        if color:
            self._status.set_text(text, color)
        else:
            self._status.set_text(text)

    def draw(self) -> None:
        self._surface.fill(COLORS["bg"])
        ctx: PaintContext = PaintContext(
            self._surface, Box(0, 0, 320, 240), Box(0, 0, 320, 240)
        )

        if self._showing_confirm:
            action_label: str = (
                "factory" if self._confirm_action == "factory" else "last stamp"
            )
            title: str = (
                f"Rollback {self._confirm_target}\nto {action_label}?"
            )
            dialog = ConfirmDialog(
                self._surface, title, self._do_confirm, self._do_cancel
            )
            dialog.draw()
            return

        self._menu.draw(ctx)
        self._status.draw(ctx)

    def handle_event(self, event: InputEvent) -> bool:
        if self._showing_confirm:
            dialog = ConfirmDialog(
                self._surface, "", self._do_confirm, self._do_cancel
            )
            return dialog.handle_event(event)

        if event == InputEvent.LONG_CLICK:
            if self._detail_index is not None:
                self._back_to_list()
                return True
            return False

        return self._menu.handle_event(event)
