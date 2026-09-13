# pyright: reportPrivateUsage=false
"""Tests for the system recovery facet (copy + hash model)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pistomp_recovery.file_facet import FileFacet, TrackedFile


@pytest.fixture
def system_facet(tmp_path: Path) -> FileFacet:
    """Return an isolated system FileFacet backed by temporary directories."""
    source = tmp_path / "system"
    repo = tmp_path / "system.git"
    source.mkdir()
    repo.mkdir()
    files = ("config.txt", "cmdline.txt", "pistomp.conf", "jackdrc", "asound.state")
    return FileFacet(
        name="system",
        repo_dir=repo,
        files=tuple(TrackedFile(name, source / name) for name in files),
    )




class TestInitSystem:
    def test_copies_existing_files_as_factory_state(self, system_facet: FileFacet) -> None:
        for file in system_facet.files:
            file.source.write_text(f"factory {file.name}")

        system_facet.init()

        for file in system_facet.files:
            assert (system_facet.repo_dir / file.name).read_text() == f"factory {file.name}"
        assert git_branch_exists(system_facet.repo_dir, "factory")

    def test_factory_branch_created_only_once(self, system_facet: FileFacet) -> None:
        first = system_facet.files[0]
        first.source.write_text("v1")

        system_facet.init()
        first.source.write_text("v2")
        system_facet.init()

        assert (system_facet.repo_dir / first.name).read_text() == "v1"


class TestDirtyDetection:
    def test_clean_when_files_match(self, system_facet: FileFacet) -> None:
        for file in system_facet.files:
            file.source.write_text("same")
        system_facet.init()

        items = {item.name: item for item in system_facet.list_items()}
        assert not any(item.dirty for item in items.values())

    def test_dirty_when_live_file_changes(self, system_facet: FileFacet) -> None:
        first = system_facet.files[0]
        first.source.write_text("same")
        system_facet.init()
        first.source.write_text("changed")

        items = {item.name: item for item in system_facet.list_items()}
        assert items[first.name].dirty


class TestStampAndRollback:
    def test_stamp_captures_current_state(self, system_facet: FileFacet) -> None:
        first = system_facet.files[0]
        first.source.write_text("v1")
        system_facet.init()
        first.source.write_text("v2")

        tag = system_facet.stamp()

        assert tag is not None
        assert len(tag) == 40  # commit hash
        assert (system_facet.repo_dir / first.name).read_text() == "v2"

    def test_rollback_to_factory_restores_changed_file(self, system_facet: FileFacet) -> None:
        first = system_facet.files[0]
        first.source.write_text("factory")
        system_facet.init()
        first.source.write_text("changed")

        system_facet.rollback(first.name, "factory")

        assert first.source.read_text() == "factory"


def git_branch_exists(repo: Path, branch: str) -> bool:
    from pistomp_recovery import git_util

    return git_util.branch_exists(repo, branch)
