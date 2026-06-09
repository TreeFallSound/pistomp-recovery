from __future__ import annotations

import pygame

from pistomp_recovery.ui.widgets.misc import Box
from pistomp_recovery.ui.widgets.paint import PaintContext
from pistomp_recovery.ui.widgets.widget import Widget


class Container(Widget):
    def __init__(self, bounds: Box) -> None:
        super().__init__(bounds)
        self.children: list[Widget] = []
        self._cache: pygame.Surface | None = None
        self._dirty_region: Box | None = self.bounds

    def add_child(self, child: Widget) -> None:
        child._parent = self
        self.children.append(child)
        child.mark_dirty()

    def remove_child(self, child: Widget) -> None:
        self.children.remove(child)
        child._parent = None
        self._dirty_region = self.bounds

    def propagate_dirty(self, region: Box) -> None:
        if self._dirty_region is None:
            self._dirty_region = region
        else:
            self._dirty_region = self._dirty_region.union(region)
        if self._parent is not None:
            self._parent.propagate_dirty(region.offset(self.bounds.x, self.bounds.y))

    def draw(self, ctx: PaintContext) -> None:
        if self._dirty_region is None:
            return

        local_clip: Box | None = self.bounds.clip(ctx.clip)
        if local_clip is None:
            return

        inner_ctx: PaintContext = PaintContext(ctx.surface, local_clip, self.bounds)

        for child in self.children:
            if not self.bounds.intersects(child.bounds):
                continue
            child_ctx: PaintContext | None = inner_ctx.painting(child.bounds)
            if child_ctx is not None:
                child.draw(child_ctx)

        self._dirty_region = None
