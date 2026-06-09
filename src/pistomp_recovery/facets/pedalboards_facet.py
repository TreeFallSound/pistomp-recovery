from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from pistomp_recovery import git_util
from pistomp_recovery.constants import PEDALBOARDS_DIR, RECOVERY_DIR
from pistomp_recovery.facets.base import Facet, FacetItem
from pistomp_recovery.util import human_time

logger = logging.getLogger(__name__)


class PedalboardItem:
    def __init__(
        self,
        name: str,
        path: Path,
        is_dirty: bool,
        last_stamp_time: datetime | None,
        last_stamp_tag: str | None,
    ) -> None:
        self.name: str = name
        self.path: Path = path
        self.is_dirty: bool = is_dirty
        self.last_stamp_time: datetime | None = last_stamp_time
        self.last_stamp_tag: str | None = last_stamp_tag

    @property
    def display_label(self) -> str:
        dirty_marker: str = "\u25cf " if self.is_dirty else "  "
        return f"{dirty_marker}{self.name}"

    @property
    def display_right(self) -> str:
        if self.last_stamp_time is None:
            return "never"
        return human_time(self.last_stamp_time)

    @property
    def display_time(self) -> str:
        if self.last_stamp_time is None:
            return "never"
        return human_time(self.last_stamp_time)

    @property
    def display_name(self) -> str:
        return self.display_label

    @property
    def version_drift(self) -> str:
        return ""


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
            git_util.git(
                "remote",
                "add",
                "upstream",
                "https://github.com/TreeFallSound/pi-stomp-pedalboards.git",
                cwd=self.path,
                check=False,
            )
            return

        self.path.mkdir(parents=True, exist_ok=True)
        git_util.git(
            "clone",
            "https://github.com/TreeFallSound/pi-stomp-pedalboards.git",
            str(self.path),
            cwd=self.path.parent,
        )
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

    def list_items(self) -> Sequence[FacetItem]:
        stamped_items: list[PedalboardItem] = []
        unstamped_items: list[PedalboardItem] = []
        if not self.path.is_dir():
            return []

        for entry in sorted(self.path.iterdir()):
            if not entry.is_dir() or not entry.name.endswith(".pedalboard"):
                continue
            name: str = entry.name
            is_dirty: bool = bool(
                git_util.git(
                    "status",
                    "--porcelain",
                    "--",
                    str(entry),
                    cwd=self.path,
                    check=False,
                ).strip()
            )

            stamp_tag: str | None = git_util.last_stamp(
                self.path,
                f"pedalboard/{name}",
            )
            stamp_time: datetime | None = None
            stamp_tag_for_item: str | None = None
            if stamp_tag:
                stamp_tag_for_item = stamp_tag
                stamp_time = _parse_stamp_time(stamp_tag)

            item: PedalboardItem = PedalboardItem(
                name=name,
                path=entry,
                is_dirty=is_dirty,
                last_stamp_time=stamp_time,
                last_stamp_tag=stamp_tag_for_item,
            )
            if stamp_time is not None:
                stamped_items.append(item)
            else:
                unstamped_items.append(item)

        stamped_items.sort(
            key=lambda i: i.last_stamp_time or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        unstamped_items.sort(key=lambda i: _dir_mtime(i.path), reverse=True)
        result: list[FacetItem] = []
        result.extend(stamped_items)
        result.extend(unstamped_items)
        return result

    def stamp_item(self, item_name: str) -> str:
        item_path: Path = self.path / item_name
        git_util.git("add", str(item_path), cwd=self.path)
        tag_name: str = git_util.stamp(self.path, f"pedalboard/{item_name}")
        return tag_name

    def rollback_item(self, item_name: str, tag: str | None = None) -> None:
        item_path: Path = self.path / item_name
        if tag:
            git_util.git("checkout", tag, "--", str(item_path), cwd=self.path)
        else:
            items = self.list_items()
            for item in items:
                if item.name == item_name and isinstance(item, PedalboardItem):
                    last_tag: str | None = item.last_stamp_tag
                    if last_tag:
                        git_util.git("checkout", last_tag, "--", str(item_path), cwd=self.path)
                    else:
                        return
                    break
            else:
                return
        git_util.add_and_commit(self.path, f"rollback {item_name}")

    def factory_reset_item(self, item_name: str) -> None:
        item_path: Path = self.path / item_name
        git_util.git("checkout", git_util.FACTORY_BRANCH, "--", str(item_path), cwd=self.path)
        git_util.add_and_commit(self.path, f"factory reset {item_name}")


def _parse_stamp_time(tag: str) -> datetime | None:
    parts: list[str] = tag.rsplit("/", 1)
    if len(parts) < 2:
        return None
    ts_str: str = parts[-1]
    try:
        return datetime.strptime(ts_str, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _dir_mtime(path: Path) -> datetime:
    try:
        from os import stat

        return datetime.fromtimestamp(stat(path).st_mtime, tz=timezone.utc)
    except OSError:
        return datetime.min.replace(tzinfo=timezone.utc)
