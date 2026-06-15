from __future__ import annotations

from typing import Callable

import pygame

from pistomp_recovery.items import Row, Target
from pistomp_recovery.service import CrashInfo
from pistomp_recovery.ui.screens.menu_screen import MenuScreen
from pistomp_recovery.ui.widgets.header import ICON_EXIT

_MAX_COLS: int = 38


class CrashScreen(MenuScreen):
    """Crash recovery: failed-service summary, last log lines, and actions.

    Reuses :class:`MenuScreen` — service/log lines are static (target-less)
    rows, and the bottom row holds the two navigable actions
    ``[RESUME] | [RECOVERY]``. The header exit icon also resumes.
    """

    def __init__(
        self,
        surface: pygame.Surface,
        on_resume: Callable[[], None],
        on_recovery: Callable[[], None],
        crash_info: CrashInfo | None = None,
    ) -> None:
        rows: list[Row] = []
        if crash_info is not None:
            for svc, state in crash_info.service_states.items():
                marker: str = "  <--" if state == "failed" else ""
                rows.append(Row(prefix=f"{svc}: {state}{marker}"[:_MAX_COLS]))
            if crash_info.crash_log:
                rows.append(Row(prefix=""))
                for line in crash_info.crash_log.split("\n")[-5:]:
                    rows.append(Row(prefix=line[:_MAX_COLS]))
            rows.append(Row(prefix=""))

        rows.append(
            Row((
                Target("RESUME", on_resume),
                Target("RECOVERY", on_recovery),
            ))
        )

        super().__init__(
            surface,
            title="pi-Stomp! Crash",
            rows=rows,
            header_icon=Target(ICON_EXIT, on_resume),
        )
