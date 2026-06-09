from __future__ import annotations

import logging
from pathlib import Path

from pistomp_recovery import git_util
from pistomp_recovery.constants import RECOVERY_DIR
from pistomp_recovery.facets.base import Facet

logger = logging.getLogger(__name__)

SYSTEM_FILES: tuple[str, ...] = (
    "/boot/config.txt",
    "/boot/cmdline.txt",
    "/boot/pistomp.conf",
    "/etc/jackdrc",
    "/var/lib/alsa/asound.state",
)


class SystemFacet(Facet):
    def __init__(self) -> None:
        super().__init__(name="system", path=Path("/etc"))
        self.repo_path: Path = Path(RECOVERY_DIR) / "system.git"

    def init(self) -> None:
        self.repo_path.mkdir(parents=True, exist_ok=True)
        if not git_util.is_repo(self.repo_path):
            git_util.init_repo(self.repo_path)

        for filepath in SYSTEM_FILES:
            src: Path = Path(filepath)
            link: Path = self.repo_path / src.name
            if src.exists() and not link.exists():
                link.symlink_to(src)

        git_util.add_and_commit(self.repo_path, "initial system config state")
        git_util.create_factory_branch(self.repo_path)

    def snapshot(self, message: str | None = None) -> str:
        git_util.add_and_commit(self.repo_path, message or "system config snapshot")
        return git_util.current_state(self.repo_path) or ""

    def stamp(self, message: str | None = None) -> str:
        return git_util.stamp(self.repo_path, self.name, message)

    def rollback(self, tag: str | None = None) -> None:
        git_util.rollback(self.repo_path, tag)

    def factory_reset(self) -> None:
        git_util.factory_reset(self.repo_path)

    def last_stamp(self) -> str | None:
        return git_util.last_stamp(self.repo_path, self.name)

    def status(self) -> str:
        return git_util.diff_summary(self.repo_path)
