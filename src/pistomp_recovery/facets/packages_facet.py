from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from pistomp_recovery.constants import (
    FACTORY_PACKAGES_FILE,
    PACKAGES_STAMP_FILE,
    PISTOMP_PACKAGES,
    RECOVERY_DIR,
)
from pistomp_recovery.facets.base import Facet, FacetItem
from pistomp_recovery.packages.manager import PackageManager
from pistomp_recovery.util import human_time

logger = logging.getLogger(__name__)


@dataclass
class PackageItem:
    name: str
    installed_version: str | None
    stamped_version: str | None
    factory_version: str | None
    available_version: str | None
    last_stamp_time: datetime | None

    @property
    def is_dirty(self) -> bool:
        if self.installed_version is None:
            return self.stamped_version is not None
        return self.installed_version != self.stamped_version

    @property
    def display_label(self) -> str:
        dirty_marker: str = "\u25cf " if self.is_dirty else "  "
        return f"{dirty_marker}{self.name}"

    @property
    def display_right(self) -> str:
        if self.available_version and self.installed_version:
            return f"\u2191{self.available_version}"
        return ""

    @property
    def display_name(self) -> str:
        return self.display_label

    @property
    def display_version(self) -> str:
        if self.installed_version is None:
            return "not installed"
        return self.installed_version

    @property
    def display_time(self) -> str:
        if self.last_stamp_time is None:
            return "never"
        return human_time(self.last_stamp_time)

    @property
    def version_drift(self) -> str:
        if self.is_dirty and self.installed_version and self.stamped_version:
            return f"{self.installed_version} \u2192 {self.stamped_version}"
        return ""


class PackagesFacet(Facet):
    def __init__(self) -> None:
        super().__init__(name="packages", path=Path(RECOVERY_DIR) / "packages")
        self._stamp_path: Path = Path(PACKAGES_STAMP_FILE)
        self._factory_path: Path = Path(FACTORY_PACKAGES_FILE)
        self._manager: PackageManager = PackageManager()

    def init(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        if not self._stamp_path.exists():
            self._write_stamp()

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

    def _read_stamp(self) -> dict[str, str]:
        if not self._stamp_path.exists():
            return {}
        try:
            data: dict[str, str] = json.loads(self._stamp_path.read_text())
            return data
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read packages stamp file")
            return {}

    def _read_factory(self) -> dict[str, str]:
        if not self._factory_path.exists():
            return {}
        try:
            data: dict[str, str] = json.loads(self._factory_path.read_text())
            return data
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read factory packages file")
            return {}

    def _write_stamp(self) -> None:
        versions: dict[str, str] = self._collect_versions()
        self._stamp_path.parent.mkdir(parents=True, exist_ok=True)
        self._stamp_path.write_text(json.dumps(versions, indent=2, sort_keys=True))

    def snapshot(self, message: str | None = None) -> str:
        self._write_stamp()
        stamp_time: str = datetime.now(timezone.utc).isoformat()
        return f"snapshot/packages/{stamp_time}"

    def stamp(self, message: str | None = None) -> str:
        self._write_stamp()
        ts: str = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        tag_name: str = f"stamp/packages/{ts}"
        return tag_name

    def rollback(self, tag: str | None = None) -> None:
        stamped: dict[str, str] = self._read_stamp()
        factory: dict[str, str] = self._read_factory()
        target: dict[str, str] = {}
        if tag:
            target = factory
        else:
            target = stamped if stamped else factory
        self._install_versions(target)

    def factory_reset(self) -> None:
        factory: dict[str, str] = self._read_factory()
        if not factory:
            logger.warning("No factory packages file, cannot reset")
            return
        self._install_versions(factory)

    def _install_versions(self, versions: dict[str, str]) -> None:
        packages: list[str] = [
            f"{name}={ver}" for name, ver in versions.items()
            if ver != "not-installed"
        ]
        if not packages:
            return
        logger.info("Installing packages: %s", packages)
        subprocess.run(
            ["pacman", "-U", "--noconfirm"] + packages,
            check=False,
        )

    def last_stamp(self) -> str | None:
        if not self._stamp_path.exists():
            return None
        try:
            mtime: float = self._stamp_path.stat().st_mtime
            ts: datetime = datetime.fromtimestamp(mtime, tz=timezone.utc)
            return f"stamp/packages/{ts.strftime('%Y%m%d-%H%M%S')}"
        except OSError:
            return None

    def status(self) -> str:
        installed: dict[str, str] = self._collect_versions()
        stamped: dict[str, str] = self._read_stamp()
        lines: list[str] = []
        for pkg in PISTOMP_PACKAGES:
            inst: str = installed.get(pkg, "not-installed")
            stamp: str = stamped.get(pkg, "?")
            marker: str = " " if inst == stamp else "*"
            lines.append(f"{marker} {pkg}: {inst} (stamped: {stamp})")
        return "\n".join(lines)

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
            if len(parts) >= 3:
                pkg: str = parts[0]
                updates.append((pkg, parts[1], parts[2]))
            elif len(parts) == 2:
                updates.append((parts[0], "unknown", parts[1]))
        return updates

    def list_items(self) -> Sequence[FacetItem]:
        installed: dict[str, str] = self._collect_versions()
        stamped: dict[str, str] = self._read_stamp()
        factory: dict[str, str] = self._read_factory()

        stamp_tag: str | None = self.last_stamp()
        stamp_time: datetime | None = None
        if stamp_tag:
            stamp_time = _parse_stamp_time(stamp_tag)

        available: dict[str, str] = {}
        try:
            for pkg_name, _old_v, new_v in self.get_available_updates():
                available[pkg_name] = new_v
        except Exception:
            pass

        items: list[PackageItem] = []
        for pkg_name in PISTOMP_PACKAGES:
            inst_ver: str | None = installed.get(pkg_name)
            if inst_ver == "not-installed":
                inst_ver = None
            stamp_ver: str | None = stamped.get(pkg_name)
            if stamp_ver == "not-installed":
                stamp_ver = None
            fact_ver: str | None = factory.get(pkg_name)
            if fact_ver == "not-installed":
                fact_ver = None
            avail_ver: str | None = available.get(pkg_name)
            items.append(PackageItem(
                name=pkg_name,
                installed_version=inst_ver,
                stamped_version=stamp_ver,
                factory_version=fact_ver,
                available_version=avail_ver,
                last_stamp_time=stamp_time,
            ))
        return items

    def rollback_item(self, item_name: str, tag: str | None = None) -> None:
        stamped: dict[str, str] = self._read_stamp()
        factory: dict[str, str] = self._read_factory()
        if tag:
            target: dict[str, str] = factory
        else:
            target = stamped if stamped else factory
        version: str | None = target.get(item_name)
        if not version or version == "not-installed":
            logger.warning("No version found for %s in target", item_name)
            return
        logger.info("Rolling back %s to %s", item_name, version)
        subprocess.run(
            ["pacman", "-U", "--noconfirm", f"{item_name}={version}"],
            check=False,
        )

    def factory_reset_item(self, item_name: str) -> None:
        factory: dict[str, str] = self._read_factory()
        version: str | None = factory.get(item_name)
        if not version or version == "not-installed":
            logger.warning("No factory version found for %s", item_name)
            return
        logger.info("Factory resetting %s to %s", item_name, version)
        subprocess.run(
            ["pacman", "-U", "--noconfirm", f"{item_name}={version}"],
            check=False,
        )


def _parse_stamp_time(tag: str) -> datetime | None:
    parts: list[str] = tag.rsplit("/", 1)
    if len(parts) < 2:
        return None
    ts_str: str = parts[-1]
    try:
        return datetime.strptime(ts_str, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
