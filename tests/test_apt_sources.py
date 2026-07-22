# pyright: reportPrivateUsage=false
"""Which sources.list.d files the restricted apt update refreshes.

The restricted update must cover every pistomp channel (`trixie` and, when the
device opted in, `trixie-testing`) while never re-hitting the big Debian/raspi
mirrors. It must ALSO never pull the pre-release suite onto a device that was
not flashed for it — which is guaranteed structurally by the fact that a
non-prerelease image simply never ships `pistomp-testing.list`.
"""

from __future__ import annotations

from pathlib import Path

from pistomp_recovery.packages.manager import pistomp_apt_source_files


def _touch(d: Path, name: str) -> None:
    (d / name).write_text("deb [arch=arm64] https://example/ trixie main\n")


def test_includes_both_pistomp_channels(tmp_path: Path) -> None:
    _touch(tmp_path, "pistomp.list")
    _touch(tmp_path, "pistomp-testing.list")
    _touch(tmp_path, "debian.sources")
    _touch(tmp_path, "raspi.sources")

    files = pistomp_apt_source_files(str(tmp_path))
    names = sorted(Path(f).name for f in files)

    assert names == ["pistomp-testing.list", "pistomp.list"]


def test_non_prerelease_image_excludes_testing(tmp_path: Path) -> None:
    # A production image ships only pistomp.list — no way to pull ~pre packages.
    _touch(tmp_path, "pistomp.list")
    _touch(tmp_path, "debian.sources")

    files = pistomp_apt_source_files(str(tmp_path))
    names = [Path(f).name for f in files]

    assert names == ["pistomp.list"]
    assert all("testing" not in n for n in names)


def test_returns_absolute_paths(tmp_path: Path) -> None:
    _touch(tmp_path, "pistomp.list")
    files = pistomp_apt_source_files(str(tmp_path))
    assert files and all(Path(f).is_absolute() for f in files)


def test_missing_dir_is_empty(tmp_path: Path) -> None:
    assert pistomp_apt_source_files(str(tmp_path / "nope")) == []
