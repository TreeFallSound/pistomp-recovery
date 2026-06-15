from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from pistomp_recovery import git_util
from pistomp_recovery.constants import RECOVERY_DIR
from pistomp_recovery.items import Action, Item
from pistomp_recovery.util import human_time

logger = logging.getLogger(__name__)

SYSTEM_FILES: tuple[str, ...] = (
    "/boot/config.txt",
    "/boot/cmdline.txt",
    "/boot/pistomp.conf",
    "/etc/jackdrc",
    "/var/lib/alsa/asound.state",
)
SYSTEM_REPO: Path = Path(RECOVERY_DIR) / "system.git"


def init_system() -> None:
    """Ensure system repo exists with factory and device branches."""
    SYSTEM_REPO.mkdir(parents=True, exist_ok=True)
    if not git_util.is_repo(SYSTEM_REPO):
        git_util.init_repo(SYSTEM_REPO)
    for filepath in SYSTEM_FILES:
        src: Path = Path(filepath)
        link: Path = SYSTEM_REPO / src.name
        if src.exists() and not link.exists():
            link.symlink_to(src)
    git_util.add_and_commit(SYSTEM_REPO, "initial system config state")
    git_util.create_factory_branch(SYSTEM_REPO)
    git_util.git("checkout", git_util.DEVICE_BRANCH, cwd=SYSTEM_REPO, check=False)


def _repo_is_dirty() -> bool:
    return bool(
        git_util.git("status", "--porcelain", cwd=SYSTEM_REPO, check=False).strip()
    )


def _repo_stamp_time() -> datetime | None:
    stamp_tag: str | None = git_util.last_stamp(SYSTEM_REPO, "system")
    return _parse_stamp_time(stamp_tag) if stamp_tag else None


def list_system_items() -> list[Item]:
    """Return one Item per system file."""
    init_system()
    repo_dirty: bool = _repo_is_dirty()
    stamp_time: datetime | None = _repo_stamp_time()

    items: list[Item] = []
    for filepath in SYSTEM_FILES:
        src: Path = Path(filepath)
        if not src.exists():
            continue

        name: str = src.name
        actions: list[Action] = []
        if stamp_time:
            actions.append(
                Action(
                    "Rollback to stamp",
                    lambda f=filepath: rollback_system_file(f, "stamp"),
                    confirm=f"Rollback {name}\nto last stamp?",
                )
            )
        actions.append(
            Action(
                "Rollback to factory",
                lambda f=filepath: rollback_system_file(f, "factory"),
                confirm=f"Reset {name}\nto factory?",
            )
        )

        items.append(
            Item(
                name=name,
                label=name + (" *" if repo_dirty else ""),
                dirty=repo_dirty,
                right=human_time(stamp_time) if stamp_time else "factory",
                actions=actions,
            )
        )
    return items


def stamp_system() -> str:
    """Commit and tag current system state."""
    init_system()
    git_util.add_and_commit(SYSTEM_REPO, "system stamp")
    return git_util.stamp(SYSTEM_REPO, "system")


def rollback_system_file(filepath: str, target: str) -> None:
    """Rollback a single system file to stamp or factory."""
    init_system()
    src: Path = Path(filepath)
    name: str = src.name
    if target == "factory":
        git_util.git(
            "checkout", git_util.FACTORY_BRANCH, "--", name, cwd=SYSTEM_REPO
        )
    else:
        tag: str | None = git_util.last_stamp(SYSTEM_REPO, "system")
        if tag:
            git_util.git("checkout", tag, "--", name, cwd=SYSTEM_REPO)
    git_util.add_and_commit(SYSTEM_REPO, f"rollback {name}")


def rollback_system(target: str) -> None:
    """Rollback all system files to stamp or factory."""
    init_system()
    if target == "factory":
        git_util.factory_reset(SYSTEM_REPO)
    else:
        tag: str | None = git_util.last_stamp(SYSTEM_REPO, "system")
        if tag:
            git_util.rollback(SYSTEM_REPO, tag)


def _parse_stamp_time(tag: str) -> datetime | None:
    parts: list[str] = tag.rsplit("/", 1)
    if len(parts) < 2:
        return None
    ts_str: str = parts[-1]
    try:
        return datetime.strptime(ts_str, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
