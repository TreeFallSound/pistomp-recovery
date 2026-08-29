# pyright: reportPrivateUsage=false
"""New-package OTA rollouts through the updates path.

`apt list --upgradeable` can only ever report installed packages, so a
brand-new repo package (e.g. pistomp-bluetooth on an already-deployed
device) was invisible to recovery regardless of channel. discover_packages
now returns the full repo set and check_updates surfaces not-installed
packages from `apt list` (which also lists available-but-not-installed
packages), with old_ver "not-installed".

Installedness is decided by dpkg, not by the `apt list` line: a package
removed but not purged (dpkg state "rc") still prints a ",now" suite
component while being entirely absent from the system.

These tests pin that contract at the manager and facet level by faking the
`apt list` and `dpkg-query` subprocess runs — the same seam test_health.py
uses for journalctl.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from pistomp_recovery.items import Item
from pistomp_recovery.packages.manager import _AVAILABLE_LINE, _UPGRADABLE_LINE, AptManager
from pistomp_recovery.packages.packages import PackageFacet


class _FakeManager:
    """PackageManager stand-in with scripted check_updates/verify output."""

    def __init__(
        self,
        updates: list[tuple[str, str, str]] | None = None,
        installed: dict[str, str] | None = None,
        unverified: tuple[str, ...] = (),
    ) -> None:
        self._updates = updates or []
        self._installed = installed or {}
        self._unverified = unverified
        self.verified: tuple[str, ...] | None = None

    def list_installed(self, names: tuple[str, ...]) -> dict[str, str]:
        return {n: self._installed.get(n, "not-installed") for n in names}

    def check_updates(self, names: tuple[str, ...]) -> list[tuple[str, str, str]]:
        return list(self._updates)

    def verify_packages(self, names: tuple[str, ...]) -> tuple[str, ...]:
        self.verified = names
        return self._unverified


APT_LIST_OUTPUT = """\
Listing...
jack2-pistomp/trixie,now 1.9.13-1 arm64 [upgradable from: 1.9.12-1]
mod-ui/trixie,now 0.14.0-1 arm64 [installed]
pi-stomp/now 3.3.0-1 arm64 [installed,local]
pistomp-bluetooth/trixie,now 1.0.0~pre1 arm64 [residual-config]
mod-midi-merger/trixie 1.0-1 arm64
wpasupplicant/trixie,now 2.11-4 arm64 [upgradable from: 2.10-3]
bash/trixie,now 5.2.32-1 arm64 [installed]
"""


# dpkg-query -W output for list_installed(). pistomp-bluetooth is "rc":
# removed but not purged, so apt still tags its line ",now".
DPKG_QUERY_OUTPUT = """\
jack2-pistomp\tii \t1.9.12-1
mod-ui\tii \t0.14.0-1
pi-stomp\tii \t3.3.0-1
pistomp-bluetooth\trc \t1.0.0~pre1
bash\tii \t5.2.32-1
"""


def _completed(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_upgradable_line_regex_matches_apt_format() -> None:
    m = _UPGRADABLE_LINE.match(
        "jack2-pistomp/trixie,now 1.9.13-1 arm64 [upgradable from: 1.9.12-1]"
    )
    assert m is not None
    assert m.group(1) == "jack2-pistomp"
    assert m.group(2) == "1.9.13-1"
    assert m.group(3) == "1.9.12-1"


def test_available_line_regex_matches_every_apt_list_shape() -> None:
    """The regex parses the line; it does not judge installedness."""
    m = _AVAILABLE_LINE.match("pistomp-bluetooth/trixie 1.0.0~pre1 arm64")
    assert m is not None
    assert (m.group(1), m.group(2), m.group(3)) == ("pistomp-bluetooth", "trixie", "1.0.0~pre1")
    # Removed-but-not-purged: a ",now" suite plus a trailing bracket group.
    # This is the shape that must still parse — dpkg decides it is absent.
    m = _AVAILABLE_LINE.match("pistomp-bluetooth/trixie,now 1.0.0~pre1 arm64 [residual-config]")
    assert m is not None
    assert (m.group(1), m.group(2), m.group(3)) == (
        "pistomp-bluetooth",
        "trixie,now",
        "1.0.0~pre1",
    )
    # Installed and dpkg-only lines parse too; check_updates filters them.
    assert _AVAILABLE_LINE.match("mod-ui/trixie,now 0.14.0-1 arm64 [installed]") is not None
    assert _AVAILABLE_LINE.match("pi-stomp/now 3.3.0-1 arm64 [installed,local]") is not None


def test_check_updates_surfaces_new_and_upgradable(monkeypatch: Any) -> None:
    """A not-installed repo package appears with old_ver 'not-installed'."""
    mgr = AptManager()
    mgr._synced = True  # skip sync_db

    def fake_run(args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return _completed(DPKG_QUERY_OUTPUT if args[0] == "dpkg-query" else APT_LIST_OUTPUT)

    monkeypatch.setattr(subprocess, "run", fake_run)
    updates = mgr.check_updates(
        (
            "jack2-pistomp",
            "mod-ui",
            "pi-stomp",
            "pistomp-bluetooth",
            "mod-midi-merger",
            "missing-pkg",
        )
    )
    by_name = {name: (old, new) for name, old, new in updates}
    assert by_name["jack2-pistomp"] == ("1.9.12-1", "1.9.13-1")  # upgradable
    # Removed-but-not-purged ("rc") is absent from the system, so it is offered
    # despite apt tagging its line ",now". This is the psdev regression.
    assert by_name["pistomp-bluetooth"] == ("not-installed", "1.0.0~pre1")
    assert by_name["mod-midi-merger"] == ("not-installed", "1.0-1")  # never installed
    # Installed-at-latest packages are not reported (apt omits them).
    assert "mod-ui" not in by_name
    # dpkg-only installed packages are not "new".
    assert "pi-stomp" not in by_name
    # Not-installed packages the repo does not offer are not reported.
    assert "missing-pkg" not in by_name
    # Off-repo upgradable packages are filtered by the name set.
    assert all(name != "wpasupplicant" for name, _, _ in updates)


def test_discover_packages_includes_not_installed(tmp_path: Path) -> None:
    """discover must return the full repo set, not the installed subset."""
    lists_dir = tmp_path / "lists"
    lists_dir.mkdir()
    # Release file with matching Origin, and its Packages file.
    (lists_dir / "treefallsound_github.io_pi-gen-pistomp_dists_trixie_Release").write_text(
        "Origin: pistomp\nLabel: pistomp\nSuite: trixie\n"
    )
    (
        lists_dir
        / "treefallsound_github.io_pi-gen-pistomp_dists_trixie_main_binary-arm64_Packages"
    ).write_text(
        "Package: pistomp-bluetooth\nVersion: 1.0.0~pre1\n\n"
        "Package: jack2-pistomp\nVersion: 1.9.13-1\n\n"
        "Package: pi-stomp\nVersion: 3.3.0-1\n"
    )
    discovered = AptManager().discover_packages("pistomp", lists_dir=str(lists_dir))
    assert discovered == ("jack2-pistomp", "pi-stomp", "pistomp-bluetooth")


def test_remote_updates_labels_new_package_without_old_version() -> None:
    """New-package rows show no old version; upgradable rows show both."""
    mgr = _FakeManager(
        updates=[
            ("jack2-pistomp", "1.9.12-1", "1.9.13-1"),
            ("pistomp-bluetooth", "not-installed", "1.0.0~pre1"),
        ]
    )
    facet = PackageFacet(mgr, ("jack2-pistomp", "pistomp-bluetooth"))  # type: ignore[arg-type]
    items = facet.remote_updates()
    assert items[0].label == "jack2-pistomp 1.9.12-1"
    assert items[0].right == "↑1.9.13-1"
    assert items[1].label == "pistomp-bluetooth"
    assert items[1].right == "↑1.0.0~pre1"
    # Two updates → "Update All" row appended.
    assert items[2].name == "all"


def test_update_item_helper_drops_not_installed_label() -> None:
    item: Item = PackageFacet._update_item("pistomp-bluetooth", "not-installed", "1.0.0")
    assert item.label == "pistomp-bluetooth"
    item = PackageFacet._update_item("mod-ui", "0.13.0-1", "0.14.0-1")
    assert item.label == "mod-ui 0.13.0-1"


def test_unverified_packages_skips_not_installed() -> None:
    """Not-installed packages must not be dpkg --verified (they error)."""
    mgr = _FakeManager(installed={"jack2-pistomp": "1.9.13-1"}, unverified=("jack2-pistomp",))
    facet = PackageFacet(mgr, ("jack2-pistomp", "pistomp-bluetooth"))  # type: ignore[arg-type]
    unverified = facet.unverified_packages()
    assert unverified == ("jack2-pistomp",)
    assert mgr.verified == ("jack2-pistomp",)
