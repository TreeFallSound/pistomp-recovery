from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

from pistomp_recovery.constants import RECOVERY_DIR


@runtime_checkable
class FacetItem(Protocol):
    name: str

    @property
    def is_dirty(self) -> bool: ...

    @property
    def display_label(self) -> str: ...

    @property
    def display_right(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    @property
    def display_time(self) -> str: ...

    @property
    def version_drift(self) -> str: ...


class Facet(ABC):
    """Part of the system that can be snapshotted, rolled back, and stamped."""

    name: str
    path: Path

    def __init__(self, name: str, path: str | Path) -> None:
        self.name = name
        self.path = Path(path)
        self.repo_path: Path = Path(RECOVERY_DIR) / f"{name}.git"

    @abstractmethod
    def init(self) -> None: ...

    @abstractmethod
    def snapshot(self, message: str | None = None) -> str: ...

    @abstractmethod
    def stamp(self, message: str | None = None) -> str: ...

    @abstractmethod
    def rollback(self, tag: str | None = None) -> None: ...

    @abstractmethod
    def factory_reset(self) -> None: ...

    @abstractmethod
    def last_stamp(self) -> str | None: ...

    @abstractmethod
    def status(self) -> str: ...

    def list_items(self) -> Sequence[FacetItem] | None:
        return None

    def stamp_item(self, item_name: str) -> str:
        raise NotImplementedError(f"{self.name} does not support item-level stamping")

    def rollback_item(self, item_name: str, tag: str | None = None) -> None:
        raise NotImplementedError(f"{self.name} does not support item-level rollback")

    def factory_reset_item(self, item_name: str) -> None:
        raise NotImplementedError(f"{self.name} does not support item-level factory reset")
