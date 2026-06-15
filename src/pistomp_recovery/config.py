from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from pistomp_recovery import git_util
from pistomp_recovery.constants import CONFIG_DIR, RECOVERY_DIR
from pistomp_recovery.items import Action, Item
from pistomp_recovery.util import human_time

logger = logging.getLogger(__name__)

CONFIG_FILES: tuple[str, ...] = (
    "default_config.yml",
    "settings.yml",
)
CONFIG_REPO: Path = Path(RECOVERY_DIR) / "config.git"


def init_config() -> None:
    """Ensure config repo exists with factory and device branches."""
    CONFIG_REPO.mkdir(parents=True, exist_ok=True)
    if not git_util.is_repo(CONFIG_REPO):
        git_util.init_repo(CONFIG_REPO)
    for filename in CONFIG_FILES:
        src: Path = Path(CONFIG_DIR) / filename
        link: Path = CONFIG_REPO / filename
        if src.exists() and not link.exists():
            link.symlink_to(src)
    git_util.add_and_commit(CONFIG_REPO, "initial config state")
    git_util.create_factory_branch(CONFIG_REPO)
    git_util.git("checkout", git_util.DEVICE_BRANCH, cwd=CONFIG_REPO, check=False)


def _repo_is_dirty() -> bool:
    return bool(
        git_util.git("status", "--porcelain", cwd=CONFIG_REPO, check=False).strip()
    )


def _repo_stamp_time() -> datetime | None:
    stamp_tag: str | None = git_util.last_stamp(CONFIG_REPO, "config")
    return _parse_stamp_time(stamp_tag) if stamp_tag else None


def list_config_items() -> list[Item]:
    """Return one Item per config file."""
    init_config()
    repo_dirty: bool = _repo_is_dirty()
    stamp_time: datetime | None = _repo_stamp_time()

    items: list[Item] = []
    for filename in CONFIG_FILES:
        src: Path = Path(CONFIG_DIR) / filename
        if not src.exists():
            continue

        actions: list[Action] = []
        if stamp_time:
            actions.append(
                Action(
                    "Rollback to stamp",
                    lambda f=filename: rollback_config_file(f, "stamp"),
                    confirm=f"Rollback {filename}\nto last stamp?",
                )
            )
        actions.append(
            Action(
                "Rollback to factory",
                lambda f=filename: rollback_config_file(f, "factory"),
                confirm=f"Reset {filename}\nto factory?",
            )
        )

        items.append(
            Item(
                name=filename,
                label=filename + (" *" if repo_dirty else ""),
                dirty=repo_dirty,
                right=human_time(stamp_time) if stamp_time else "factory",
                actions=actions,
            )
        )
    return items


def stamp_config() -> str:
    """Commit and tag current config state."""
    init_config()
    git_util.add_and_commit(CONFIG_REPO, "config stamp")
    return git_util.stamp(CONFIG_REPO, "config")


def rollback_config_file(filename: str, target: str) -> None:
    """Rollback a single config file to stamp or factory."""
    init_config()
    if target == "factory":
        git_util.git(
            "checkout", git_util.FACTORY_BRANCH, "--", filename, cwd=CONFIG_REPO
        )
    else:
        tag: str | None = git_util.last_stamp(CONFIG_REPO, "config")
        if tag:
            git_util.git("checkout", tag, "--", filename, cwd=CONFIG_REPO)
    git_util.add_and_commit(CONFIG_REPO, f"rollback {filename}")


def rollback_config(target: str) -> None:
    """Rollback all config files to stamp or factory."""
    init_config()
    if target == "factory":
        git_util.factory_reset(CONFIG_REPO)
    else:
        tag: str | None = git_util.last_stamp(CONFIG_REPO, "config")
        if tag:
            git_util.rollback(CONFIG_REPO, tag)


def _parse_stamp_time(tag: str) -> datetime | None:
    parts: list[str] = tag.rsplit("/", 1)
    if len(parts) < 2:
        return None
    ts_str: str = parts[-1]
    try:
        return datetime.strptime(ts_str, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
