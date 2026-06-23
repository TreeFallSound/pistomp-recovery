from __future__ import annotations

import logging
import shutil
from pathlib import Path

from pistomp_recovery.constants import (
    PATCHSTORAGE_MARKER,
    PLUGINS_CACHE_WARN_BYTES,
    PLUGINS_DIR,
)
from pistomp_recovery.facet import RollbackTarget
from pistomp_recovery.items import Action, Item
from pistomp_recovery.util import human_size

logger = logging.getLogger(__name__)


def _dir_size(path: Path) -> int:
    """Total size in bytes of all files under ``path`` (symlinks not followed)."""
    total: int = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file() and not entry.is_symlink():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


class PluginFacet:
    """Recovery facet for user-installed LV2 plugins.

    Plugins are delivered and updated by mod-ui's PatchStorage downloader, not
    by recovery, so this facet has no stamp/checkpoint or update concept. Its
    only job is **factory reset**: removing user-installed bundles to reclaim
    space and return to the factory plugin set.

    A bundle counts as user-installed (and therefore removable) when it carries
    the ``patchstorage.json`` marker mod-ui writes on install. Factory plugins
    live in the system LV2 path, outside ``PLUGINS_DIR``, and are never touched.
    """

    name = "plugins"
    default_path: Path = Path(PLUGINS_DIR)

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self.default_path

    def init(self) -> None:
        # The plugins dir is created by mod-ui on first install; nothing to set
        # up here. Kept for Facet-protocol compatibility.
        return None

    def _user_bundles(self) -> list[Path]:
        """Return LV2 bundle dirs carrying the PatchStorage marker, sorted by name."""
        if not self.path.is_dir():
            return []
        bundles: list[Path] = []
        for entry in sorted(self.path.iterdir()):
            if entry.is_dir() and (entry / PATCHSTORAGE_MARKER).is_file():
                bundles.append(entry)
        return bundles

    def cache_size(self) -> int:
        """Total bytes occupied by user-installed plugin bundles."""
        return sum(_dir_size(b) for b in self._user_bundles())

    def over_cap(self) -> bool:
        """True if the plugins cache exceeds the soft warning threshold."""
        return self.cache_size() > PLUGINS_CACHE_WARN_BYTES

    def cache_summary(self) -> str:
        """Short right-aligned badge for the Plugins menu line (size, with ⚠ if over cap)."""
        bundles = self._user_bundles()
        if not bundles:
            return ""
        size = sum(_dir_size(b) for b in bundles)
        label = human_size(size)
        return f"{label} ⚠" if size > PLUGINS_CACHE_WARN_BYTES else label

    def remote_updates(self) -> list[Item]:
        """Plugin updates are owned by mod-ui's PatchStorage downloader, not recovery."""
        return []

    def stamp(self) -> str | None:
        # Plugins are not versioned by recovery; there is no checkpoint to take.
        return None

    def list_items(self) -> list[Item]:
        items: list[Item] = []
        for bundle in self._user_bundles():
            name = bundle.name
            items.append(
                Item(
                    name=name,
                    label=name,
                    dirty=True,
                    right=human_size(_dir_size(bundle)),
                    actions=[
                        Action(
                            "Rollback to factory",
                            lambda n=name: self.rollback(n, "factory"),
                            confirm=f"Remove {name}\nfrom this device?",
                        ),
                    ],
                )
            )
        return items

    def remove_bundle(self, name: str) -> None:
        """Delete a single user-installed bundle by directory name."""
        bundle = self.path / name
        if (bundle / PATCHSTORAGE_MARKER).is_file():
            shutil.rmtree(bundle, ignore_errors=True)
            logger.info("Removed plugin bundle %s", name)
        else:
            logger.warning("Refusing to remove %s: not a PatchStorage bundle", name)

    def reset_all(self) -> None:
        """Remove every user-installed bundle, returning to the factory plugin set."""
        for bundle in self._user_bundles():
            self.remove_bundle(bundle.name)

    def rollback(self, name: str, target: RollbackTarget) -> None:
        # Plugins have no per-stamp history; both targets mean "remove the
        # user-installed bundle and fall back to factory."
        self.remove_bundle(name)


def make_plugin_facet(path: Path | None = None) -> PluginFacet:
    """Return a fresh plugin facet for registration by an entry point."""
    return PluginFacet(path)
