# pyright: reportPrivateUsage=false
"""Tests for DOMAIN_FACETS aggregation and action routing in both backends.

Covers: item aggregation across multiple facets per domain, action closure
binding (boot rollback doesn't touch config files and vice versa), and the
orphaned-packages fix (System domain now surfaces package updates/rollbacks).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from pistomp_recovery.emulator.backends import EmulatorDataBackend


@pytest.fixture(scope="class")
def data() -> Iterator[EmulatorDataBackend]:
    backend = EmulatorDataBackend()
    yield backend
    backend.cleanup()


# ---------------------------------------------------------------------------
# Config domain — aggregates config facet + boot facet
# ---------------------------------------------------------------------------


class TestConfigDomainAggregation:
    def test_factory_reset_config_includes_app_yaml_files(
        self, data: EmulatorDataBackend
    ) -> None:
        items = data.domain_items("factory", "config")
        names = {it.name for it in items}
        assert "default_config.yml" in names
        assert "settings.yml" in names

    def test_factory_reset_config_includes_boot_files(
        self, data: EmulatorDataBackend
    ) -> None:
        items = data.domain_items("factory", "config")
        names = {it.name for it in items}
        assert "config.txt" in names
        assert "jackdrc" in names

    def test_config_item_names_are_unique(self, data: EmulatorDataBackend) -> None:
        """Merged Config list must have no duplicate item names."""
        items = data.domain_items("factory", "config")
        names = [it.name for it in items]
        assert len(names) == len(set(names)), f"Duplicate item names in Config: {names}"

    def test_checkpoint_config_shows_dirty_files_from_both_facets(
        self, data: EmulatorDataBackend
    ) -> None:
        # EmulatorDataBackend starts with settings.yml and config.txt dirty.
        items = data.domain_items("checkpoint", "config")
        names = {it.name for it in items}
        assert "settings.yml" in names
        assert "default_config.yml" in names
        assert "config.txt" in names

    def test_updates_config_is_empty(self, data: EmulatorDataBackend) -> None:
        """File facets have no remote updates — Config shows nothing in Updates mode."""
        items = data.domain_items("updates", "config")
        assert items == []


# ---------------------------------------------------------------------------
# System domain — maps to packages facet only
# ---------------------------------------------------------------------------


class TestSystemDomainPackages:
    def test_updates_system_shows_package_updates(
        self, data: EmulatorDataBackend
    ) -> None:
        items = data.domain_items("updates", "system")
        assert len(items) >= 1
        names = {it.name for it in items}
        # EmulatorPackageFacet seeds jack2-pistomp and mod-ui as pending updates
        assert "jack2-pistomp" in names

    def test_factory_system_shows_package_rollback_items(
        self, data: EmulatorDataBackend
    ) -> None:
        items = data.domain_items("factory", "system")
        assert len(items) > 0
        for it in items:
            labels = {a.label for a in it.actions}
            assert "Rollback to factory" in labels

    def test_system_contains_no_file_facet_items(
        self, data: EmulatorDataBackend
    ) -> None:
        file_names = {
            "default_config.yml", "settings.yml",
            "config.txt", "cmdline.txt", "jackdrc",
        }
        for mode in ("factory", "checkpoint", "updates"):
            items = data.domain_items(mode, "system")
            names = {it.name for it in items}
            overlap = names & file_names
            assert not overlap, (
                f"File-facet items leaked into System domain ({mode} mode): {overlap}"
            )


# ---------------------------------------------------------------------------
# Action routing — rollback closures are facet-bound after aggregation
# ---------------------------------------------------------------------------


class TestActionRouting:
    def test_factory_rollback_of_boot_file_does_not_touch_config_file(
        self, data: EmulatorDataBackend, tmp_path: Path
    ) -> None:
        """Rollback action on config.txt (boot facet) must not affect settings.yml."""
        settings_before = data._config_dir / "settings.yml"
        config_txt = data._system_dir / "config.txt"
        settings_content_before = settings_before.read_text()

        # Find the factory rollback action for config.txt in Config domain
        items = data.domain_items("factory", "config")
        config_item = next((it for it in items if it.name == "config.txt"), None)
        assert config_item is not None, "config.txt not found in Config factory items"
        rollback_action = next(
            (a for a in config_item.actions if a.label == "Rollback to factory"), None
        )
        assert rollback_action is not None

        # Execute the rollback
        rollback_action.callback()

        # config.txt should be restored to factory content
        assert config_txt.read_text() == "# factory config.txt\n"
        # settings.yml must be untouched
        assert settings_before.read_text() == settings_content_before

    def test_factory_rollback_of_config_file_does_not_touch_boot_file(
        self, data: EmulatorDataBackend, tmp_path: Path
    ) -> None:
        """Rollback action on settings.yml (config facet) must not affect config.txt."""
        config_txt = data._system_dir / "config.txt"
        config_txt_before = config_txt.read_text()

        items = data.domain_items("factory", "config")
        settings_item = next((it for it in items if it.name == "settings.yml"), None)
        assert settings_item is not None
        rollback_action = next(
            (a for a in settings_item.actions if a.label == "Rollback to factory"), None
        )
        assert rollback_action is not None

        rollback_action.callback()

        # settings.yml restored
        settings = data._config_dir / "settings.yml"
        assert settings.read_text() == "# factory settings\n"
        # config.txt untouched
        assert config_txt.read_text() == config_txt_before


# ---------------------------------------------------------------------------
# No orphan facets — guard mirroring test_constants.py but at runtime
# ---------------------------------------------------------------------------


class TestNoOrphanFacets:
    def test_all_registered_facets_are_reachable(
        self, data: EmulatorDataBackend
    ) -> None:
        """Every facet registered by EmulatorDataBackend must be reachable from a domain."""
        from pistomp_recovery.constants import DOMAIN_FACETS
        from pistomp_recovery.facet import all_facets

        registered = set(all_facets().keys())
        reachable = {f for facets in DOMAIN_FACETS.values() for f in facets}
        orphans = registered - reachable
        assert not orphans, f"Registered facets reachable from no domain: {orphans}"
