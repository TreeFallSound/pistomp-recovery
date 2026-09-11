from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable

from pistomp_recovery import git_util
from pistomp_recovery.facet import RollbackTarget
from pistomp_recovery.items import Action, Item
from pistomp_recovery.util import human_time

logger = logging.getLogger(__name__)


class MissingFactoryBaseline(Enum):
    """What factory rollback means when an old repo lacks a tracked file."""

    DELETE = "delete"
    ADOPT_LIVE = "adopt-live"


RestorePolicy = Callable[[str, str, RollbackTarget], str | None]
FactoryBaselineStale = Callable[[str], bool]


@dataclass(frozen=True)
class TrackedFile:
    """One live file and the business rules for restoring it."""

    name: str
    source: Path
    display_name: str | None = None
    restore: RestorePolicy | None = None
    missing_factory_baseline: MissingFactoryBaseline = MissingFactoryBaseline.DELETE
    factory_baseline_is_stale: FactoryBaselineStale | None = None

    @property
    def label(self) -> str:
        return self.display_name or self.name


def _file_equal(a: Path, b: Path) -> bool:
    """Return True if both paths exist with identical content, or both are missing."""
    if a.exists() != b.exists():
        return False
    if not a.exists():
        return True
    return a.read_bytes() == b.read_bytes()


class FileFacet:
    """Recovery facet for files tracked by a small git repository.

    The facet owns repository mechanics. ``TrackedFile.restore`` contains any
    domain-specific rule for turning a checked-out file into the live file.
    """

    name: str

    def __init__(
        self,
        *,
        name: str,
        repo_dir: Path,
        files: tuple[TrackedFile, ...],
    ) -> None:
        self.name = name
        self.repo_dir = repo_dir
        self.files = files
        self._files_by_name = {file.name: file for file in files}

    def file(self, name: str) -> TrackedFile:
        """Return the tracked-file definition for ``name``."""
        return self._files_by_name[name]
    def _needs_factory_migration(self, file: TrackedFile) -> bool:
        if not file.source.exists():
            return False
        if not self._exists_in_ref(file.name, git_util.FACTORY_BRANCH):
            return file.missing_factory_baseline == MissingFactoryBaseline.ADOPT_LIVE
        if file.factory_baseline_is_stale is None:
            return False
        factory = git_util.git(
            "show", f"{git_util.FACTORY_BRANCH}:{file.name}", cwd=self.repo_dir
        )
        return file.factory_baseline_is_stale(factory)

    def _repo_path(self, filename: str) -> Path:
        return self.repo_dir / filename

    def _copy_to_repo(self, file: TrackedFile) -> None:
        """Copy the live file into the repo, or remove it if the live file is gone."""
        dst = self._repo_path(file.name)
        if file.source.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file.source, dst)
        elif dst.exists():
            dst.unlink()

    def _restore_to_live(self, file: TrackedFile, target: RollbackTarget) -> None:
        """Restore one checked-out repo file according to its business policy."""
        restored = self._repo_path(file.name)
        live = file.source
        if not restored.exists():
            if live.exists():
                live.unlink()
            return

        if file.restore is None or not live.exists():
            live.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(restored, live)
            return

        try:
            replacement = file.restore(restored.read_text(), live.read_text(), target)
        except (OSError, UnicodeDecodeError):
            logger.warning("cannot read %s as text; copying it verbatim", file.name)
            live.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(restored, live)
            return

        if replacement is None:
            logger.warning("restore policy declined %s; leaving the live file as-is", file.name)
            return
        live.write_text(replacement)

    def snapshot(self) -> None:
        for file in self.files:
            self._copy_to_repo(file)

    def init_repo(self) -> None:
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        if not git_util.is_repo(self.repo_dir):
            git_util.init_repo(self.repo_dir)

        if not git_util.branch_exists(self.repo_dir, git_util.FACTORY_BRANCH):
            self.snapshot()
            git_util.add_and_commit(self.repo_dir, f"initial {self.name} state")
            git_util.create_factory_branch(self.repo_dir)

        git_util.git("checkout", git_util.DEVICE_BRANCH, cwd=self.repo_dir, check=False)

    def migrate_factory_baseline(self) -> None:
        """Adopt live baselines for files added or invalidated by an upgrade.

        This is an explicit migration for repositories created by older
        recovery versions. It is intentionally not part of observation methods
        such as ``list_items``.
        """
        self.init_repo()
        migrations = [file for file in self.files if self._needs_factory_migration(file)]
        if not migrations:
            return

        names = ", ".join(file.name for file in migrations)
        logger.info("seeding factory state for %s: %s", self.name, names)
        for file in migrations:
            self._copy_to_repo(file)
        git_util.add_and_commit(self.repo_dir, f"track new {self.name} files")
        git_util.git("checkout", git_util.FACTORY_BRANCH, cwd=self.repo_dir)
        for file in migrations:
            self._copy_to_repo(file)
        git_util.add_and_commit(self.repo_dir, f"seed factory {self.name} state")
        git_util.git("checkout", git_util.DEVICE_BRANCH, cwd=self.repo_dir)

    # Facet protocol aliases
    init = init_repo

    def remote_updates(self) -> list[Item]:
        return []

    def rollback(self, name: str, target: RollbackTarget) -> None:
        self.rollback_file(name, target)

    def stamp_time(self) -> datetime | None:
        return git_util.last_commit_time(self.repo_dir)

    def stamp(self) -> str | None:
        self.init_repo()
        self.snapshot()
        return git_util.add_and_commit(self.repo_dir, f"{self.name} stamp")

    def _exists_in_ref(self, filename: str, ref: str) -> bool:
        """Return True if ``filename`` is tracked in ``ref``."""
        result: str = git_util.git("ls-tree", ref, "--", filename, cwd=self.repo_dir, check=False)
        return bool(result.strip())

    def _delete_from_repo(self, filename: str) -> None:
        repo_file = self._repo_path(filename)
        if repo_file.exists():
            repo_file.unlink()

    def rollback_file(self, filename: str, target: RollbackTarget) -> None:
        """Rollback a single file to stamp or factory."""
        self.init_repo()
        file = self.file(filename)
        ref = git_util.FACTORY_BRANCH if target == "factory" else "HEAD"
        if self._exists_in_ref(filename, ref):
            git_util.git("checkout", ref, "--", filename, cwd=self.repo_dir)
        else:
            self._delete_from_repo(filename)
        self._restore_to_live(file, target)
        self._copy_to_repo(file)
        git_util.add_and_commit(self.repo_dir, f"rollback {filename}")

    def rollback_all(self, target: RollbackTarget) -> None:
        """Rollback all files to stamp or factory."""
        self.init_repo()
        ref = git_util.FACTORY_BRANCH if target == "factory" else "HEAD"
        git_util.git("checkout", ref, "--", ".", cwd=self.repo_dir)
        for file in self.files:
            if not self._exists_in_ref(file.name, ref):
                self._delete_from_repo(file.name)
            self._restore_to_live(file, target)
            self._copy_to_repo(file)
        git_util.add_and_commit(self.repo_dir, f"rollback to {ref}")

    def list_items(self) -> list[Item]:
        self.init_repo()
        stamp_time = self.stamp_time()

        items: list[Item] = []
        for file in self.files:
            repo_copy = self._repo_path(file.name)
            if not file.source.exists() and not repo_copy.exists():
                continue

            dirty = not _file_equal(file.source, repo_copy)
            actions: list[Action] = []
            if stamp_time:
                actions.append(
                    Action(
                        "Rollback to stamp",
                        lambda f=file.name: self.rollback_file(f, "stamp"),
                        confirm=f"Rollback {file.label}\nto last stamp?",
                    )
                )
            actions.append(
                Action(
                    "Rollback to factory",
                    lambda f=file.name: self.rollback_file(f, "factory"),
                    confirm=f"Reset {file.label}\nto factory?",
                )
            )

            items.append(
                Item(
                    name=file.label,
                    label=file.label + (" *" if dirty else ""),
                    dirty=dirty,
                    right=human_time(stamp_time) if stamp_time else "factory",
                    actions=actions,
                )
            )
        return items
