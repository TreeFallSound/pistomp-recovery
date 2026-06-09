from __future__ import annotations

from pistomp_recovery.ui.widgets.container import Container
from pistomp_recovery.ui.widgets.misc import Box, InputEvent
from pistomp_recovery.ui.widgets.paint import PaintContext


class PanelStack(Container):
    def __init__(self, width: int, height: int) -> None:
        super().__init__(Box(0, 0, width, height))
        self._panels: list[Container] = []

    def push(self, panel: Container) -> None:
        panel._parent = self
        self._panels.append(panel)
        self.children = list(self._panels)
        panel.mark_dirty()

    def pop(self) -> Container | None:
        if not self._panels:
            return None
        panel: Container = self._panels.pop()
        panel._parent = None
        self.children = list(self._panels)
        self.mark_dirty()
        return panel

    @property
    def top(self) -> Container | None:
        return self._panels[-1] if self._panels else None

    def draw(self, ctx: PaintContext) -> None:
        full: PaintContext = PaintContext(
            ctx.surface, Box(0, 0, self.bounds.w, self.bounds.h), self.bounds
        )
        for panel in self._panels:
            panel.draw(full)

        self._dirty_region = None
        self._surface_needs_update: bool = True

    def propagate_dirty(self, region: Box) -> None:
        if self._dirty_region is None:
            self._dirty_region = region
        else:
            self._dirty_region = self._dirty_region.union(region)

    def handle_event(self, event: InputEvent) -> bool:
        if self._panels:
            last: Container = self._panels[-1]
            return last.handle_event(event)
        return False
