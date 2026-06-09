from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pygame

from pistomp_recovery.ui.colors import COLORS
from pistomp_recovery.ui.screens import Screen
from pistomp_recovery.ui.widgets.confirm_dialog import ConfirmDialog
from pistomp_recovery.ui.widgets.menu import Menu
from pistomp_recovery.ui.widgets.misc import Box, InputEvent
from pistomp_recovery.ui.widgets.paint import PaintContext
from pistomp_recovery.ui.widgets.text import StatusLine


@dataclass
class DirtyItem:
    label: str
    right: str
    kind: str
    name: str


class ResetScreen(Screen):
    def __init__(
        self,
        surface: pygame.Surface,
        items: list[DirtyItem],
        on_rollback_stamp: Callable[[str, str], None] | None = None,
        on_rollback_factory: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__(surface)
        self._items: list[DirtyItem] = items
        self._on_rollback_stamp: Callable[[str, str], None] | None = on_rollback_stamp
        self._on_rollback_factory: Callable[[str, str], None] | None = on_rollback_factory
        self._menu: Menu = Menu(Box(4, 24, 312, 180), title="Reset")
        self._status: StatusLine = StatusLine(Box(4, 210, 312, 22))
        self._detail_item: DirtyItem | None = None
        self._showing_confirm: bool = False
        self._confirm_action: str = ""
        self._build_menu()

    def _build_menu(self) -> None:
        self._menu.clear_items()
        for item in self._items:
            self._menu.add_item(item.label, lambda i=item: self._select_item(i), item.right)
        self._menu.add_item("\u2190 Back", self._go_back)

    def _select_item(self, item: DirtyItem) -> None:
        self._detail_item = item
        self._build_detail_menu()

    def _build_detail_menu(self) -> None:
        if self._detail_item is None:
            return
        self._menu.clear_items()
        self._menu.add_item("Rollback to stamp", self._rollback_stamp)
        self._menu.add_item("Rollback to factory", self._rollback_factory)
        self._menu.add_item("\u2190 Back", self._back_to_list)

    def _rollback_stamp(self) -> None:
        if self._detail_item is None:
            return
        assert self._detail_item is not None
        self._showing_confirm = True
        self._confirm_action = "stamp"

    def _rollback_factory(self) -> None:
        if self._detail_item is None:
            return
        self._showing_confirm = True
        self._confirm_action = "factory"

    def _back_to_list(self) -> None:
        self._detail_item = None
        self._build_menu()

    def _go_back(self) -> None:
        if self._on_back is not None:
            self._on_back()

    def _do_confirm(self) -> None:
        if self._detail_item is None:
            self._showing_confirm = False
            return
        if self._confirm_action == "stamp" and self._on_rollback_stamp:
            self._on_rollback_stamp(self._detail_item.kind, self._detail_item.name)
        elif self._confirm_action == "factory" and self._on_rollback_factory:
            self._on_rollback_factory(self._detail_item.kind, self._detail_item.name)
        self._showing_confirm = False

    def _do_cancel(self) -> None:
        self._showing_confirm = False

    def draw(self) -> None:
        self._surface.fill(COLORS["bg"])
        ctx: PaintContext = PaintContext(
            self._surface, Box(0, 0, 320, 240), Box(0, 0, 320, 240)
        )

        if self._showing_confirm and self._detail_item is not None:
            title: str = f"Rollback {self._detail_item.label}\nto {self._confirm_action}?"
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
            if self._detail_item is not None:
                self._back_to_list()
                return True
            return False

        return self._menu.handle_event(event)
