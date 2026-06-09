from __future__ import annotations

from pistomp_recovery.ui.widgets.misc import Box, InputEvent
from pistomp_recovery.ui.widgets.paint import PaintContext


class Widget:
    def __init__(self, bounds: Box) -> None:
        self.bounds: Box = bounds
        self._dirty: bool = True
        self._parent: Widget | None = None

    def mark_dirty(self, region: Box | None = None) -> None:
        self._dirty = True
        dirty_region: Box = region if region is not None else self.bounds
        if self._parent is not None:
            self._parent.propagate_dirty(
                dirty_region.offset(self.bounds.x, self.bounds.y)
            )

    def propagate_dirty(self, region: Box) -> None:
        pass

    def handle_event(self, event: InputEvent) -> bool:
        return False

    def draw(self, ctx: PaintContext) -> None:
        raise NotImplementedError
