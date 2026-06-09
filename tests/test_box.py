"""Box unit tests — geometry operations. No pygame needed."""

from __future__ import annotations

from pistomp_recovery.ui.widgets.misc import Box


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
