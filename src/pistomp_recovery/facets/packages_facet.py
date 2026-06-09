from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from pistomp_recovery import git_util
from pistomp_recovery.constants import PISTOMP_PACKAGES, RECOVERY_DIR
from pistomp_recovery.facets.base import Facet

logger = logging.getLogger(__name__)

MANIFEST_FILENAME: str = "packages.json"


class PackagesFacet(Facet):
    def __init__(self) -> None:
        super().__init__(name="packages", path=Path(RECOVERY_DIR) / "packages")
        self.repo_path: Path = Path(RECOVERY_DIR) / "packages.git"

    def init(self) -> None:
        self.repo_path.mkdir(parents=True, exist_ok=True)
        if not git_util.is_repo(self.repo_path):
            git_util.init_repo(self.repo_path)
        self._write_manifest()
        git_util.add_and_commit(self.repo_path, "initial package manifest")
        git_util.create_factory_branch(self.repo_path)

    def _write_manifest(self) -> None:
        manifest: dict[str, str] = self._collect_versions()
        manifest_path: Path = self.repo_path / MANIFEST_FILENAME
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))

    def _collect_versions(self) -> dict[str, str]:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["pacman", "-Q"],
            capture_output=True,
            text=True,
        )
        all_packages: dict[str, str] = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts: list[str] = line.split(None, 1)
            if len(parts) == 2:
                all_packages[parts[0]] = parts[1]

        tracked: dict[str, str] = {}
        for pkg in PISTOMP_PACKAGES:
            if pkg in all_packages:
                tracked[pkg] = all_packages[pkg]
            else:
                tracked[pkg] = "not-installed"
        return tracked

    def snapshot(self, message: str | None = None) -> str:
        self._write_manifest()
        git_util.add_and_commit(self.repo_path, message or "package manifest snapshot")
        return git_util.current_state(self.repo_path) or ""

    def stamp(self, message: str | None = None) -> str:
        self._write_manifest()
        return git_util.stamp(self.repo_path, self.name, message)

    def rollback(self, tag: str | None = None) -> None:
        git_util.rollback(self.repo_path, tag)
        self._apply_manifest()

    def factory_reset(self) -> None:
        git_util.factory_reset(self.repo_path)
        self._apply_manifest()

    def last_stamp(self) -> str | None:
        return git_util.last_stamp(self.repo_path, self.name)

    def status(self) -> str:
        self._write_manifest()
        return git_util.diff_summary(self.repo_path)

    def _apply_manifest(self) -> None:
        manifest_path: Path = self.repo_path / MANIFEST_FILENAME
        if not manifest_path.exists():
            logger.warning("No package manifest found for rollback")
            return
        manifest: dict[str, str] = json.loads(manifest_path.read_text())
        packages_to_install: list[str] = [
            f"{name}={ver}" for name, ver in manifest.items() if ver != "not-installed"
        ]
        if not packages_to_install:
            return
        logger.info("Rolling back packages: %s", packages_to_install)
        subprocess.run(
            ["pacman", "-U", "--noconfirm"] + packages_to_install,
            check=False,
        )

    def get_installed_version(self, package: str) -> str | None:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["pacman", "-Q", package],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        parts: list[str] = result.stdout.strip().split(None, 1)
        return parts[1] if len(parts) == 2 else None

    def get_available_updates(self) -> list[tuple[str, str, str]]:
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
            if len(parts) >= 2:
                pkg: str = parts[0]
                old_ver: str = parts[1] if len(parts) >= 3 else "unknown"
                new_ver: str = parts[2] if len(parts) >= 3 else parts[1]
                updates.append((pkg, old_ver, new_ver))
        return updates
