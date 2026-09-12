# pyright: reportPrivateUsage=false
"""Tests for the boot recovery facet (copy + hash model)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pistomp_recovery import boot
from pistomp_recovery.file_facet import TrackedFile

PLAIN = "cmdline.txt"

FACTORY_CONFIG = """\
[all]
# Enable the sound card (uncomment only one)
#dtoverlay=audioinjector-wm8731-audio
dtoverlay=iqaudio-codec
#dtoverlay=hifiberry-dacplusadc

gpu_mem=16
"""


@pytest.fixture
def boot_facet(tmp_path: Path) -> boot.BootFacet:
    """Return an isolated BootFacet backed by temporary directories."""
    source = tmp_path / "system"
    repo = tmp_path / "system.git"
    source.mkdir()
    repo.mkdir()

    firmware = source / "boot" / "firmware"
    default = source / "etc" / "default"
    var = source / "var" / "lib" / "alsa"
    firmware.mkdir(parents=True)
    default.mkdir(parents=True)
    var.mkdir(parents=True)

    paths = {
        "config.txt": firmware / "config.txt",
        "cmdline.txt": firmware / "cmdline.txt",
        "pistomp.conf": firmware / "pistomp.conf",
        "jack": default / "jack",
        "asound.state": var / "asound.state",
    }
    return boot.BootFacet(
        name="boot",
        repo_dir=repo,
        files=tuple(
            TrackedFile(name=file.name, source=paths[file.name], display_name=file.display_name)
            for file in boot.BOOT_FILES
        ),
    )


def write_all(facet: boot.BootFacet, text: str) -> None:
    for file in facet.files:
        file.source.write_text(FACTORY_CONFIG if file.name == "config.txt" else text)


class TestInitBoot:
    def test_copies_existing_files_as_factory_state(self, boot_facet: boot.BootFacet) -> None:
        write_all(boot_facet, "factory")

        boot_facet.init()

        assert (boot_facet.repo_dir / PLAIN).read_text() == "factory"
        assert (boot_facet.repo_dir / "config.txt").read_text() == FACTORY_CONFIG
        assert git_branch_exists(boot_facet.repo_dir, "factory")

    def test_factory_branch_created_only_once(self, boot_facet: boot.BootFacet) -> None:
        boot_facet.file(PLAIN).source.write_text("v1")

        boot_facet.init()
        boot_facet.file(PLAIN).source.write_text("v2")
        boot_facet.init()

        assert (boot_facet.repo_dir / PLAIN).read_text() == "v1"


class TestDirtyDetection:
    def test_clean_when_files_match(self, boot_facet: boot.BootFacet) -> None:
        write_all(boot_facet, "same")
        boot_facet.init()

        items = {item.name: item for item in boot_facet.list_items()}
        assert not any(item.dirty for item in items.values())

    def test_dirty_when_live_file_changes(self, boot_facet: boot.BootFacet) -> None:
        boot_facet.file(PLAIN).source.write_text("same")
        boot_facet.init()
        boot_facet.file(PLAIN).source.write_text("changed")

        items = {item.name: item for item in boot_facet.list_items()}
        assert items[PLAIN].dirty


class TestStampAndRollback:
    def test_stamp_captures_current_state(self, boot_facet: boot.BootFacet) -> None:
        boot_facet.file(PLAIN).source.write_text("v1")
        boot_facet.init()
        boot_facet.file(PLAIN).source.write_text("v2")

        tag = boot_facet.stamp()

        assert tag is not None
        assert len(tag) == 40  # commit hash
        assert (boot_facet.repo_dir / PLAIN).read_text() == "v2"

    def test_rollback_to_factory_restores_changed_file(self, boot_facet: boot.BootFacet) -> None:
        boot_facet.file(PLAIN).source.write_text("factory")
        boot_facet.init()
        boot_facet.file(PLAIN).source.write_text("changed")

        boot_facet.rollback(PLAIN, "factory")

        assert boot_facet.file(PLAIN).source.read_text() == "factory"


class TestAudioCardPreservation:
    def config_txt(self, facet: boot.BootFacet) -> Path:
        return facet.file("config.txt").source

    def test_factory_rollback_keeps_the_fitted_card(self, boot_facet: boot.BootFacet) -> None:
        live = self.config_txt(boot_facet)
        write_all(boot_facet, "factory")
        boot_facet.init()

        # The user swaps to a HiFiBerry and bumps an unrelated setting.
        live.write_text(
            FACTORY_CONFIG.replace("dtoverlay=iqaudio-codec", "#dtoverlay=iqaudio-codec")
            .replace("#dtoverlay=hifiberry-dacplusadc", "dtoverlay=hifiberry-dacplusadc")
            .replace("gpu_mem=16", "gpu_mem=128")
        )

        boot_facet.rollback("config.txt", "factory")

        text = live.read_text()
        assert "\ndtoverlay=hifiberry-dacplusadc\n" in text
        assert "\n#dtoverlay=iqaudio-codec\n" in text
        assert "gpu_mem=16" in text  # everything else did reset

    def test_rollback_leaves_repo_matching_live(self, boot_facet: boot.BootFacet) -> None:
        live = self.config_txt(boot_facet)
        write_all(boot_facet, "factory")
        boot_facet.init()
        live.write_text(
            FACTORY_CONFIG.replace("dtoverlay=iqaudio-codec", "#dtoverlay=iqaudio-codec").replace(
                "#dtoverlay=hifiberry-dacplusadc", "dtoverlay=hifiberry-dacplusadc"
            )
        )

        boot_facet.rollback("config.txt", "factory")

        items = {item.name: item for item in boot_facet.list_items()}
        assert not items["config.txt"].dirty

    def test_unknown_card_leaves_config_untouched(self, boot_facet: boot.BootFacet) -> None:
        live = self.config_txt(boot_facet)
        write_all(boot_facet, "factory")
        boot_facet.init()
        # A card this build has never heard of: no known overlay is active.
        user_text = FACTORY_CONFIG.replace(
            "dtoverlay=iqaudio-codec", "#dtoverlay=iqaudio-codec\ndtoverlay=allo-boss-dac"
        )
        live.write_text(user_text)

        boot_facet.rollback("config.txt", "factory")

        assert live.read_text() == user_text


class TestUpgradeFromOlderFileList:
    """Deploying a build that tracks files the existing factory branch predates."""

    def upgraded(self, boot_facet: boot.BootFacet) -> boot.BootFacet:
        """Init a facet tracking only asound.state, then widen it to the full list."""
        boot_facet.file("asound.state").source.write_text("alsa state\n")
        narrow = boot.BootFacet(
            name="boot",
            repo_dir=boot_facet.repo_dir,
            files=(boot_facet.file("asound.state"),),
        )
        narrow.init()
        boot_facet.file("asound.state").source.write_text("dirty before migration\n")
        boot_facet.file("config.txt").source.write_text(FACTORY_CONFIG)
        boot_facet.migrate_factory_baseline()
        return boot_facet

    def test_moved_config_placeholder_is_replaced(self, boot_facet: boot.BootFacet) -> None:
        live = boot_facet.file("config.txt").source
        live.write_text(
            "DO NOT EDIT THIS FILE\n"
            "The file you are looking for has moved to /boot/firmware/config.txt\n"
        )
        legacy = boot.BootFacet(
            name="boot",
            repo_dir=boot_facet.repo_dir,
            files=(TrackedFile("config.txt", live),),
        )
        legacy.init()
        live.write_text(FACTORY_CONFIG)

        boot_facet.migrate_factory_baseline()

        assert (boot_facet.repo_dir / "config.txt").read_text() == FACTORY_CONFIG


    def test_migration_does_not_capture_dirty_existing_files(
        self, boot_facet: boot.BootFacet
    ) -> None:
        facet = self.upgraded(boot_facet)

        assert (facet.repo_dir / "asound.state").read_text() == "alsa state\n"


    def test_factory_rollback_does_not_delete_a_newly_tracked_file(
        self, boot_facet: boot.BootFacet
    ) -> None:
        facet = self.upgraded(boot_facet)
        live = facet.file("config.txt").source

        facet.rollback("config.txt", "factory")

        assert live.exists(), "factory rollback deleted a file the factory branch predates"

    def test_newly_tracked_file_gets_its_current_content_as_baseline(
        self, boot_facet: boot.BootFacet
    ) -> None:
        facet = self.upgraded(boot_facet)
        live = facet.file("config.txt").source
        live.write_text(FACTORY_CONFIG.replace("gpu_mem=16", "gpu_mem=128"))

        facet.rollback("config.txt", "factory")

        assert live.read_text() == FACTORY_CONFIG

    def test_card_is_preserved_on_an_upgraded_device(self, boot_facet: boot.BootFacet) -> None:
        facet = self.upgraded(boot_facet)
        live = facet.file("config.txt").source
        live.write_text(
            FACTORY_CONFIG.replace("dtoverlay=iqaudio-codec", "#dtoverlay=iqaudio-codec").replace(
                "#dtoverlay=hifiberry-dacplusadc", "dtoverlay=hifiberry-dacplusadc"
            )
        )

        facet.rollback("config.txt", "factory")

        assert "\ndtoverlay=hifiberry-dacplusadc\n" in live.read_text()

    def test_untouched_files_keep_their_original_factory_baseline(
        self, boot_facet: boot.BootFacet
    ) -> None:
        facet = self.upgraded(boot_facet)
        alsa = facet.file("asound.state").source
        alsa.write_text("drifted\n")

        facet.rollback("asound.state", "factory")

        assert alsa.read_text() == "alsa state\n"


def git_branch_exists(repo: Path, branch: str) -> bool:
    from pistomp_recovery import git_util

    return git_util.branch_exists(repo, branch)
