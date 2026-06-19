"""Backend protocols for the recovery UI.

The recovery application is intentionally a black box around the device:
`RecoveryAppCore` owns the LCD menu flow and delegates every side effect to
injected backends.  Real device code uses SPI/GPIO/pacman/systemd
implementations; the emulator uses pygame, fake input, and in-memory stubs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

import pygame

from pistomp_recovery.items import Item
from pistomp_recovery.service import CrashInfo
from pistomp_recovery.ui.widgets.misc import InputEvent


@runtime_checkable
class DisplayBackend(Protocol):
    """LCD bridge: a pygame Surface that can be flushed to hardware."""

    @property
    def surface(self) -> pygame.Surface: ...

    def init(self) -> None: ...

    def update(self, surface: pygame.Surface) -> None: ...


@runtime_checkable
class InputBackend(Protocol):
    """Encoder + switch input source."""

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def poll(self) -> list[InputEvent]: ...


ProgressCallback = Callable[[str, float, str, bool], None]


@runtime_checkable
class DataBackend(Protocol):
    """Source of recoverable domains and the actions that mutate them."""

    def domains(self) -> tuple[tuple[str, str], ...]:
        """Return (domain_id, domain_label) pairs in menu order."""
        ...

    def domain_items(self, mode: str, domain: str) -> list[Item]:
        """Items for a domain in the given mode (checkpoint/factory/updates)."""
        ...

    def install_packages(
        self,
        packages: list[str],
        progress: ProgressCallback,
    ) -> bool:
        """Download, install, and stamp the given packages.

        Backends may run this on a worker thread; progress() must be safe to
        call from that thread.  The return value is True on success.
        """
        ...


@runtime_checkable
class ServiceBackend(Protocol):
    """System-level integration: lifecycle, crash info, and recovery build id."""

    def stop_main_app(self) -> bool: ...

    def start_main_app(self) -> bool: ...

    def restart_jack(self) -> bool: ...

    def restart_mod(self) -> bool: ...

    def reboot(self) -> None: ...

    def power_off(self) -> None: ...

    def recovery_sha(self) -> str: ...

    def crash_info(self) -> CrashInfo | None:
        """Crash diagnostics when booting into recovery, or None if unavailable."""
        ...


@dataclass(frozen=True)
class AppBackends:
    """Container so entry points can inject all backends at once."""

    display: DisplayBackend
    input: InputBackend
    data: DataBackend
    services: ServiceBackend
