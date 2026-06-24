# pyright: reportPrivateUsage=false
"""Tests for the boot recovery facet (copy + hash model)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pistomp_recovery import boot


@pytest.fixture
def boot_facet(tmp_path: Path) -> boot.FileFacet:
    """Return an isolated boot FileFacet backed by temp directories."""
    source = tmp_path / "system"
    repo = tmp_path / "system.git"
    source.mkdir()
    repo.mkdir()

    # Map the absolute system paths used by the module into our temp tree.
    boot_dir = source / "boot"
    etc = source / "etc"
    var = source / "var" / "lib" / "alsa"
    boot_dir.mkdir()
    etc.mkdir()
    var.mkdir(parents=True)

    test_files = {
        "config.txt": str(boot_dir / "config.txt"),
        "cmdline.txt": str(boot_dir / "cmdline.txt"),
        "pistomp.conf": str(boot_dir / "pistomp.conf"),
        "jackdrc": str(etc / "jackdrc"),
        "asound.state": str(var / "asound.state"),
    }

    return boot.FileFacet(
        name="boot",
        repo_dir=repo,
        files=tuple(test_files.keys()),
        source_resolver=lambda name: Path(test_files[name]),
        display_name_resolver=lambda name: name,
    )


class TestInitBoot:
    def test_copies_existing_files_as_factory_state(
        self, boot_facet: boot.FileFacet
    ) -> None:
        for filename in boot_facet.files:
            Path(boot_facet._source_path(filename)).write_text(
                f"factory {filename}"
            )

        boot_facet.init()

        for filename in boot_facet.files:
            assert (boot_facet.repo_dir / filename).read_text() == f"factory {filename}"
        assert git_branch_exists(boot_facet.repo_dir, "factory")

    def test_factory_branch_created_only_once(
        self, boot_facet: boot.FileFacet
    ) -> None:
        first = boot_facet.files[0]
        Path(boot_facet._source_path(first)).write_text("v1")

        boot_facet.init()
        Path(boot_facet._source_path(first)).write_text("v2")
        boot_facet.init()

        assert (boot_facet.repo_dir / first).read_text() == "v1"


class TestDirtyDetection:
    def test_clean_when_files_match(self, boot_facet: boot.FileFacet) -> None:
        for filename in boot_facet.files:
            Path(boot_facet._source_path(filename)).write_text("same")
        boot_facet.init()

        items = {item.name: item for item in boot_facet.list_items()}
        assert not any(item.dirty for item in items.values())

    def test_dirty_when_live_file_changes(
        self, boot_facet: boot.FileFacet
    ) -> None:
        first = boot_facet.files[0]
        Path(boot_facet._source_path(first)).write_text("same")
        boot_facet.init()
        Path(boot_facet._source_path(first)).write_text("changed")

        items = {item.name: item for item in boot_facet.list_items()}
        assert items[first].dirty


class TestStampAndRollback:
    def test_stamp_captures_current_state(
        self, boot_facet: boot.FileFacet
    ) -> None:
        first = boot_facet.files[0]
        Path(boot_facet._source_path(first)).write_text("v1")
        boot_facet.init()
        Path(boot_facet._source_path(first)).write_text("v2")

        tag = boot_facet.stamp()

        assert tag is not None
        assert len(tag) == 40  # commit hash
        assert (boot_facet.repo_dir / first).read_text() == "v2"

    def test_rollback_to_factory_restores_changed_file(
        self, boot_facet: boot.FileFacet
    ) -> None:
        first = boot_facet.files[0]
        Path(boot_facet._source_path(first)).write_text("factory")
        boot_facet.init()
        Path(boot_facet._source_path(first)).write_text("changed")

        boot_facet.rollback(first, "factory")

        assert Path(boot_facet._source_path(first)).read_text() == "factory"


def git_branch_exists(repo: Path, branch: str) -> bool:
    from pistomp_recovery import git_util

    return git_util.branch_exists(repo, branch)
