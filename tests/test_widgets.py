"""Widget snapshot tests for pistomp-recovery.

Each test draws a widget arrangement and asserts the output matches
a stored PNG snapshot. Run with --snapshot-update to regenerate.
"""

from __future__ import annotations

from typing import Callable

import pygame
import pytest

from pistomp_recovery.constants import LCD_HEIGHT, LCD_WIDTH
from pistomp_recovery.ui.colors import COLORS
from pistomp_recovery.ui.widgets.menu import Menu
from pistomp_recovery.ui.widgets.misc import Box, InputEvent
from pistomp_recovery.ui.widgets.paint import PaintContext
from pistomp_recovery.ui.widgets.panel import Panel
from pistomp_recovery.ui.widgets.text import ProgressBar, StatusLine, TextWidget
from tests.conftest import FakeLcd


@pytest.fixture
def surface() -> pygame.Surface:
    return pygame.Surface((LCD_WIDTH, LCD_HEIGHT))


class TestMenuWidget:
    def test_menu_items(
        self, surface: pygame.Surface, fake_lcd: FakeLcd, snapshot: Callable[..., None]
    ) -> None:
        menu: Menu = Menu(Box(4, 4, 312, 232), title="Recovery")
        menu.add_item("Resume", lambda: None)
        menu.add_item("System Info", lambda: None)
        menu.add_item("Package Updates", lambda: None)
        menu.add_item("Config Management", lambda: None)
        menu.add_item("Factory Reset", lambda: None)
        menu.add_item("Reboot", lambda: None)
        menu.add_item("Power Off", lambda: None)

        surface.fill(COLORS["bg"])
        ctx: PaintContext = PaintContext(
            surface, Box(0, 0, LCD_WIDTH, LCD_HEIGHT),
            Box(0, 0, LCD_WIDTH, LCD_HEIGHT),
        )
        menu.draw(ctx)
        fake_lcd.update(surface)
        snapshot()

    def test_menu_scroll(
        self, surface: pygame.Surface, fake_lcd: FakeLcd, snapshot: Callable[..., None]
    ) -> None:
        menu: Menu = Menu(Box(4, 4, 312, 100), title="Select")
        for i in range(20):
            menu.add_item(f"Item {i + 1}", lambda: None)
        for _ in range(10):
            menu.handle_event(InputEvent.RIGHT)
        for _ in range(2):
            menu.handle_event(InputEvent.LEFT)

        surface.fill(COLORS["bg"])
        ctx: PaintContext = PaintContext(
            surface, Box(0, 0, LCD_WIDTH, LCD_HEIGHT),
            Box(0, 0, LCD_WIDTH, LCD_HEIGHT),
        )
        menu.draw(ctx)
        fake_lcd.update(surface)
        snapshot("scrolled")


class TestProgressBar:
    def test_empty_progress(
        self, surface: pygame.Surface, fake_lcd: FakeLcd, snapshot: Callable[..., None]
    ) -> None:
        bar: ProgressBar = ProgressBar(Box(20, 100, 280, 30))
        surface.fill(COLORS["bg"])
        ctx: PaintContext = PaintContext(
            surface, Box(0, 0, LCD_WIDTH, LCD_HEIGHT),
            Box(0, 0, LCD_WIDTH, LCD_HEIGHT),
        )
        bar.draw(ctx)
        fake_lcd.update(surface)
        snapshot()

    def test_half_progress(
        self, surface: pygame.Surface, fake_lcd: FakeLcd, snapshot: Callable[..., None]
    ) -> None:
        bar: ProgressBar = ProgressBar(
            Box(20, 100, 280, 30), progress=0.5, label="Installing..."
        )
        surface.fill(COLORS["bg"])
        ctx: PaintContext = PaintContext(
            surface, Box(0, 0, LCD_WIDTH, LCD_HEIGHT),
            Box(0, 0, LCD_WIDTH, LCD_HEIGHT),
        )
        bar.draw(ctx)
        fake_lcd.update(surface)
        snapshot()

    def test_full_progress(
        self, surface: pygame.Surface, fake_lcd: FakeLcd, snapshot: Callable[..., None]
    ) -> None:
        bar: ProgressBar = ProgressBar(
            Box(20, 100, 280, 30), progress=1.0, label="Complete"
        )
        surface.fill(COLORS["bg"])
        ctx: PaintContext = PaintContext(
            surface, Box(0, 0, LCD_WIDTH, LCD_HEIGHT),
            Box(0, 0, LCD_WIDTH, LCD_HEIGHT),
        )
        bar.draw(ctx)
        fake_lcd.update(surface)
        snapshot()


class TestStatusLine:
    def test_status_text(
        self, surface: pygame.Surface, fake_lcd: FakeLcd, snapshot: Callable[..., None]
    ) -> None:
        status: StatusLine = StatusLine(
            Box(4, 210, 312, 22), text="3 updates available"
        )
        surface.fill(COLORS["bg"])
        ctx: PaintContext = PaintContext(
            surface, Box(0, 0, LCD_WIDTH, LCD_HEIGHT),
            Box(0, 0, LCD_WIDTH, LCD_HEIGHT),
        )
        status.draw(ctx)
        fake_lcd.update(surface)
        snapshot()

    def test_error_status(
        self, surface: pygame.Surface, fake_lcd: FakeLcd, snapshot: Callable[..., None]
    ) -> None:
        status: StatusLine = StatusLine(
            Box(4, 210, 312, 22),
            text="Download failed",
            color=COLORS["text_error"],
        )
        surface.fill(COLORS["bg"])
        ctx: PaintContext = PaintContext(
            surface, Box(0, 0, LCD_WIDTH, LCD_HEIGHT),
            Box(0, 0, LCD_WIDTH, LCD_HEIGHT),
        )
        status.draw(ctx)
        fake_lcd.update(surface)
        snapshot()


class TestTextWidget:
    def test_simple_text(
        self, surface: pygame.Surface, fake_lcd: FakeLcd, snapshot: Callable[..., None]
    ) -> None:
        text: TextWidget = TextWidget(
            Box(10, 10, 300, 30), "Hello, pi-Stomp!"
        )
        surface.fill(COLORS["bg"])
        ctx: PaintContext = PaintContext(
            surface, Box(0, 0, LCD_WIDTH, LCD_HEIGHT),
            Box(0, 0, LCD_WIDTH, LCD_HEIGHT),
        )
        text.draw(ctx)
        fake_lcd.update(surface)
        snapshot()


class TestPanel:
    def test_titled_panel(
        self, surface: pygame.Surface, fake_lcd: FakeLcd, snapshot: Callable[..., None]
    ) -> None:
        panel: Panel = Panel(Box(4, 4, 312, 232), title="System Info")
        info: TextWidget = TextWidget(
            Box(10, 30, 300, 20), "Kernel: 6.18.33"
        )
        panel.add_child(info)

        surface.fill(COLORS["bg"])
        ctx: PaintContext = PaintContext(
            surface, Box(0, 0, LCD_WIDTH, LCD_HEIGHT),
            Box(0, 0, LCD_WIDTH, LCD_HEIGHT),
        )
        panel.draw(ctx)
        fake_lcd.update(surface)
        snapshot()
