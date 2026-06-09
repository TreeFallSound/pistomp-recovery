from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pistomp_recovery.constants import RECOVERY_DIR


class Facet(ABC):
    """Part of the system that can be snapshotted, rolled back, and stamped."""

    name: str
    path: Path
    repo_path: Path

    def __init__(self, name: str, path: Path) -> None:
        self.name = name
        self.path = Path(path)
        self.repo_path = Path(RECOVERY_DIR) / f"{name}.git"

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
