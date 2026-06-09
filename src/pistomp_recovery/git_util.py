from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from pistomp_recovery.constants import DEVICE_BRANCH, FACTORY_BRANCH

logger = logging.getLogger(__name__)


class GitError(Exception):
    pass


def git(*args: str, cwd: str | Path, check: bool = True) -> str:
    result: subprocess.CompletedProcess[str] = subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def is_repo(path: Path) -> bool:
    return (path / ".git").is_dir() or (path / "HEAD").exists()


def init_repo(path: Path) -> None:
    if not (path / ".git").is_dir():
        path.mkdir(parents=True, exist_ok=True)
        git("init", "--initial-branch", DEVICE_BRANCH, cwd=path)
        git("config", "user.email", "recovery@pistomp.local", cwd=path)
        git("config", "user.name", "pistomp-recovery", cwd=path)


def add_and_commit(path: Path, message: str) -> None:
    git("add", "-A", cwd=path)
    status: str = git("status", "--porcelain", cwd=path, check=False)
    if not status:
        logger.debug("No changes to commit in %s", path)
        return
    git("commit", "-m", message, cwd=path)


def stamp(
    path: Path,
    tag_prefix: str,
    message: str | None = None,
) -> str:
    ts: str = _timestamp()
    tag_name: str = f"stamp/{tag_prefix}/{ts}"
    add_and_commit(path, message or f"stamp {tag_prefix} {ts}")
    git("tag", tag_name, cwd=path)
    return tag_name


def rollback(path: Path, tag: str | None = None, branch: str = FACTORY_BRANCH) -> None:
    target_ref: str = tag if tag else branch
    git("checkout", DEVICE_BRANCH, cwd=path)
    git("checkout", target_ref, "--", ".", cwd=path)
    add_and_commit(path, f"rollback to {target_ref}")


def factory_reset(path: Path) -> None:
    git("checkout", FACTORY_BRANCH, "--", ".", cwd=path)
    add_and_commit(path, "factory reset")


def last_stamp(path: Path, tag_prefix: str) -> str | None:
    tags: str = git("tag", "-l", f"stamp/{tag_prefix}/*", cwd=path, check=False)
    if not tags:
        return None
    tag_list: list[str] = tags.strip().split("\n") if tags.strip() else []
    return tag_list[-1] if tag_list else None


def all_stamps(path: Path, tag_prefix: str) -> list[str]:
    tags: str = git("tag", "-l", f"stamp/{tag_prefix}/*", cwd=path, check=False)
    if not tags:
        return []
    return [t for t in tags.strip().split("\n") if t.strip()]


def current_state(path: Path) -> str | None:
    try:
        return git("rev-parse", "HEAD", cwd=path)
    except GitError:
        return None


def diff_summary(path: Path) -> str:
    status: str = git("status", "--porcelain", cwd=path, check=False)
    return status


def create_factory_branch(path: Path) -> None:
    if DEVICE_BRANCH == "main" or DEVICE_BRANCH == "master":
        git("checkout", "-b", FACTORY_BRANCH, cwd=path)
    else:
        current: str = git("branch", "--show-current", cwd=path, check=False)
        if current != FACTORY_BRANCH:
            git("branch", FACTORY_BRANCH, cwd=path)
    git("checkout", DEVICE_BRANCH, cwd=path)


def _timestamp() -> str:
    import datetime
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
