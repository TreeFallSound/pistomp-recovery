from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from enum import Enum, auto

from pistomp_recovery.constants import PISTOMP_PACKAGES

logger = logging.getLogger(__name__)


class UpdateState(Enum):
    IDLE = auto()
    DOWNLOADING = auto()
    INSTALLING = auto()
    HEALTH_CHECKING = auto()
    STAMPING = auto()
    ROLLING_BACK = auto()
    DONE = auto()
    FAILED = auto()


@dataclass
class UpdateResult:
    state: UpdateState = UpdateState.IDLE
    packages_updated: list[str] = field(default_factory=list[str])
    error: str | None = None
    rolled_back: bool = False


class PackageManager:
    def __init__(self) -> None:
        self._state: UpdateState = UpdateState.IDLE
        self._progress: float = 0.0
        self._status_text: str = ""
        self._result: UpdateResult = UpdateResult()

    @property
    def state(self) -> UpdateState:
        return self._state

    @property
    def progress(self) -> float:
        return self._progress

    @property
    def status_text(self) -> str:
        return self._status_text

    @property
    def result(self) -> UpdateResult:
        return self._result

    def check_updates(self) -> list[tuple[str, str, str]]:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["pacman", "-Qu", *PISTOMP_PACKAGES],
            capture_output=True,
            text=True,
        )
        updates: list[tuple[str, str, str]] = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts: list[str] = line.split()
            if len(parts) >= 3:
                updates.append((parts[0], parts[1], parts[2]))
            elif len(parts) == 2:
                updates.append((parts[0], "unknown", parts[1]))
        return updates

    def download_packages(self, packages: list[str]) -> bool:
        self._state = UpdateState.DOWNLOADING
        self._progress = 0.0
        self._status_text = f"Downloading {len(packages)} packages..."

        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["pacman", "-Sw", "--noconfirm", "--needed"] + packages,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self._status_text = f"Download failed: {result.stderr.strip()}"
            self._state = UpdateState.FAILED
            logger.error("Package download failed: %s", result.stderr)
            return False

        self._progress = 0.5
        return True

    def install_packages(self, packages: list[str]) -> bool:
        self._state = UpdateState.INSTALLING
        self._progress = 0.5
        self._status_text = f"Installing {len(packages)} packages..."

        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["pacman", "-S", "--noconfirm", "--needed"] + packages,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self._status_text = f"Install failed: {result.stderr.strip()}"
            self._state = UpdateState.FAILED
            logger.error("Package install failed: %s", result.stderr)
            return False

        self._result.packages_updated = packages
        self._progress = 0.75
        return True

    def install_from_cache(self, packages: list[str]) -> bool:
        self._state = UpdateState.ROLLING_BACK
        self._progress = 0.0
        self._status_text = f"Rolling back {len(packages)} packages..."

        cached: list[str] = []
        for pkg in packages:
            cache_result: subprocess.CompletedProcess[str] = subprocess.run(
                ["pacman", "-Qp", f"/var/cache/pacman/pkg/{pkg}-*.pkg.tar*"],
                capture_output=True,
                text=True,
            )
            if cache_result.returncode == 0:
                cached.append(pkg)

        if not cached:
            self._status_text = "No cached packages for rollback"
            logger.warning("No cached packages found for rollback")
            return False

        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["pacman", "-U", "--noconfirm"] + cached,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error("Rollback install failed: %s", result.stderr)
            return False

        self._result.rolled_back = True
        self._progress = 1.0
        return True
