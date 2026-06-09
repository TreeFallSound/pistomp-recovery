"""InputEvent, Box, and PaintContext tests."""

from __future__ import annotations

import pygame

from pistomp_recovery.pygame_init import init as _pg_init
from pistomp_recovery.ui.widgets.misc import Box, InputEvent
from pistomp_recovery.ui.widgets.paint import PaintContext

_pg_init()


class TestInputEvent:
    def test_event_values(self) -> None:
        assert InputEvent.LEFT.value != InputEvent.RIGHT.value
        assert InputEvent.CLICK.value != InputEvent.LONG_CLICK.value
        assert InputEvent.BACK.value != InputEvent.CLICK.value


class TestBox:
    def test_contains(self) -> None:
        b = Box(10, 20, 30, 40)
        assert b.contains(10, 20) is True
        assert b.contains(39, 59) is True
        assert b.contains(40, 60) is False
        assert b.contains(5, 25) is False

    def test_intersects(self) -> None:
        a = Box(0, 0, 10, 10)
        b = Box(5, 5, 10, 10)
        assert a.intersects(b) is True
        assert b.intersects(a) is True

        c = Box(20, 20, 10, 10)
        assert a.intersects(c) is False

    def test_union(self) -> None:
        a = Box(0, 0, 10, 10)
        b = Box(5, 5, 10, 10)
        u = a.union(b)
        assert u == Box(0, 0, 15, 15)

    def test_clip(self) -> None:
        a = Box(0, 0, 10, 10)
        b = Box(5, 5, 10, 10)
        c = a.clip(b)
        assert c is not None
        assert c == Box(5, 5, 5, 5)

        d = a.clip(Box(20, 20, 10, 10))
        assert d is None

    def test_offset(self) -> None:
        b = Box(10, 20, 30, 40)
        o = b.offset(5, -3)
        assert o == Box(15, 17, 30, 40)

    def test_right_bottom(self) -> None:
        b = Box(10, 20, 30, 40)
        assert b.right == 40
        assert b.bottom == 60


class TestPaintContext:
    def test_painting_child_within_bounds(self) -> None:
        surface = pygame.Surface((320, 240))
        parent_ctx = PaintContext(
            surface, Box(0, 0, 320, 240), Box(0, 0, 320, 240)
        )
        child_frame = Box(10, 10, 100, 50)
        child_ctx = parent_ctx.painting(child_frame)

        assert child_ctx is not None
        assert child_ctx.frame == child_frame
        assert child_ctx.clip.x >= parent_ctx.clip.x
        assert child_ctx.clip.y >= parent_ctx.clip.y

    def test_painting_child_outside_bounds(self) -> None:
        surface = pygame.Surface((320, 240))
        parent_ctx = PaintContext(
            surface, Box(10, 10, 50, 50), Box(10, 10, 50, 50)
        )
        child_frame = Box(100, 100, 50, 50)
        child_ctx = parent_ctx.painting(child_frame)
        assert child_ctx is None
