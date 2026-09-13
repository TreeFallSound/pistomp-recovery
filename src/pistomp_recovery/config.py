from __future__ import annotations

from pathlib import Path

from pistomp_recovery.constants import CONFIG_DIR, RECOVERY_DIR
from pistomp_recovery.file_facet import FileFacet, TrackedFile

CONFIG_REPO: Path = Path(RECOVERY_DIR) / "config.git"

CONFIG_FILES: tuple[TrackedFile, ...] = (
    TrackedFile("default_config.yml", Path(CONFIG_DIR) / "default_config.yml"),
    TrackedFile("settings.yml", Path(CONFIG_DIR) / "settings.yml"),
)


def make_config_facet() -> FileFacet:
    """Return a config FileFacet for registration by an entry point."""
    return FileFacet(name="config", repo_dir=CONFIG_REPO, files=CONFIG_FILES)
