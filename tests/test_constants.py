"""Tests for constants and PACKAGE_SERVICES."""

from __future__ import annotations

from pistomp_recovery.constants import PACKAGE_SERVICES, PISTOMP_SERVICES, services_for_packages


class TestPackageServices:
    def test_known_package_returns_mapped_services(self) -> None:
        result: list[str] = services_for_packages(["jack2-pistomp"])
        assert result == ["jack", "mod-host", "mod-ui", "mod-ala-pi-stomp"]

    def test_pi_stomp_returns_its_service(self) -> None:
        result: list[str] = services_for_packages(["pi-stomp"])
        assert result == ["mod-ala-pi-stomp"]

    def test_unknown_package_returns_full_chain(self) -> None:
        result: list[str] = services_for_packages(["some-unknown-pkg"])
        assert result == list(PISTOMP_SERVICES)

    def test_multiple_packages_ordered(self) -> None:
        result: list[str] = services_for_packages(
            ["mod-host-pistomp", "pi-stomp"]
        )
        assert result == ["mod-host", "mod-ui", "mod-ala-pi-stomp"]

    def test_empty_list_returns_empty(self) -> None:
        result: list[str] = services_for_packages([])
        assert result == []

    def test_pistomp_recovery_returns_empty(self) -> None:
        result: list[str] = services_for_packages(["pistomp-recovery"])
        assert result == []

    def test_all_pistomp_packages_have_entries(self) -> None:
        from pistomp_recovery.constants import PISTOMP_PACKAGES
        for pkg in PISTOMP_PACKAGES:
            assert pkg in PACKAGE_SERVICES
