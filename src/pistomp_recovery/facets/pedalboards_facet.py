from __future__ import annotations

import logging
from pathlib import Path

from pistomp_recovery import git_util
from pistomp_recovery.constants import PEDALBOARDS_DIR, RECOVERY_DIR
from pistomp_recovery.facets.base import Facet

logger = logging.getLogger(__name__)


class PedalboardsFacet(Facet):
    def __init__(self) -> None:
        super().__init__(name="pedalboards", path=PEDALBOARDS_DIR)
        self.repo_path: Path = Path(RECOVERY_DIR) / "pedalboards.git"

    def init(self) -> None:
        self.repo_path.mkdir(parents=True, exist_ok=True)

        if git_util.is_repo(self.path):
            try:
                git_util.git("checkout", git_util.DEVICE_BRANCH, cwd=self.path)
            except git_util.GitError:
                git_util.git("checkout", "-b", git_util.DEVICE_BRANCH, cwd=self.path)
            git_util.git("remote", "add", "upstream",
                         "https://github.com/TreeFallSound/pi-stomp-pedalboards.git",
                         cwd=self.path, check=False)
            return

        self.path.mkdir(parents=True, exist_ok=True)
        git_util.git("clone",
                     "https://github.com/TreeFallSound/pi-stomp-pedalboards.git",
                     str(self.path),
                     cwd=self.path.parent)
        git_util.git("checkout", "-b", git_util.DEVICE_BRANCH, cwd=self.path)
        git_util.git("branch", git_util.FACTORY_BRANCH, cwd=self.path)

    def snapshot(self, message: str | None = None) -> str:
        git_util.add_and_commit(self.path, message or "pedalboards snapshot")
        return git_util.current_state(self.path) or ""

    def stamp(self, message: str | None = None) -> str:
        return git_util.stamp(self.path, self.name, message)

    def rollback(self, tag: str | None = None) -> None:
        git_util.rollback(self.path, tag)

    def factory_reset(self) -> None:
        git_util.factory_reset(self.path)

    def last_stamp(self) -> str | None:
        return git_util.last_stamp(self.path, self.name)

    def status(self) -> str:
        return git_util.diff_summary(self.path)
