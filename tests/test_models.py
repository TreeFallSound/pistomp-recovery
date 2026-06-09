"""Unit tests for data models and utilities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from pistomp_recovery.facets.packages_facet import PackageItem
from pistomp_recovery.facets.pedalboards_facet import PedalboardItem
from pistomp_recovery.util import human_time


class TestHumanTime:
    def test_just_now(self) -> None:
        now: datetime = datetime.now(timezone.utc)
        assert human_time(now) == "just now"

    def test_seconds_ago(self) -> None:
        now: datetime = datetime.now(timezone.utc)
        ts: datetime = now - timedelta(seconds=30)
        assert human_time(ts) == "just now"

    def test_minutes_ago(self) -> None:
        now: datetime = datetime.now(timezone.utc)
        ts: datetime = now - timedelta(minutes=42)
        assert human_time(ts) == "42m ago"

    def test_hours_ago(self) -> None:
        now: datetime = datetime.now(timezone.utc)
        ts: datetime = now - timedelta(hours=3)
        assert human_time(ts) == "3h ago"

    def test_days_ago(self) -> None:
        now: datetime = datetime.now(timezone.utc)
        ts: datetime = now - timedelta(days=2)
        assert human_time(ts) == "2 days ago"

    def test_one_day_ago(self) -> None:
        now: datetime = datetime.now(timezone.utc)
        ts: datetime = now - timedelta(days=1)
        assert human_time(ts) == "1 day ago"

    def test_weeks_ago_same_year(self) -> None:
        ts: datetime = datetime(2026, 5, 20, tzinfo=timezone.utc)
        result: str = human_time(ts)
        assert "May" in result
        assert "2026" not in result

    def test_weeks_ago_different_year(self) -> None:
        ts: datetime = datetime(2024, 12, 25, tzinfo=timezone.utc)
        result: str = human_time(ts)
        assert "Dec" in result
        assert "2024" in result

    def test_naive_datetime_treated_as_utc(self) -> None:
        ts: datetime = datetime(2026, 6, 9, 12, 0, 0)
        result: str = human_time(ts)
        assert isinstance(result, str)

    def test_future_time_treated_as_just_now(self) -> None:
        now: datetime = datetime.now(timezone.utc)
        ts: datetime = now + timedelta(minutes=5)
        assert human_time(ts) == "just now"


class TestPedalboardItem:
    def test_display_label_dirty(self) -> None:
        item: PedalboardItem = PedalboardItem(
            name="AmpBud.pedalboard",
            path=Path("/tmp/AmpBud.pedalboard"),
            is_dirty=True,
            last_stamp_time=datetime(2026, 6, 9, 10, 0, tzinfo=timezone.utc),
            last_stamp_tag="stamp/pedalboard/AmpBud.pedalboard/20260609-100000",
        )
        assert "\u25cf" in item.display_label
        assert "AmpBud" in item.display_label

    def test_display_label_clean(self) -> None:
        item: PedalboardItem = PedalboardItem(
            name="Beths.pedalboard",
            path=Path("/tmp/Beths.pedalboard"),
            is_dirty=False,
            last_stamp_time=datetime(2026, 6, 8, tzinfo=timezone.utc),
            last_stamp_tag=None,
        )
        assert "\u25cf" not in item.display_label
        assert "Beths" in item.display_label

    def test_display_time_never(self) -> None:
        item: PedalboardItem = PedalboardItem(
            name="factory-defaults.pedalboard",
            path=Path("/tmp/factory-defaults.pedalboard"),
            is_dirty=False,
            last_stamp_time=None,
            last_stamp_tag=None,
        )
        assert item.display_time == "never"


class TestPackageItem:
    def test_is_dirty_when_versions_differ(self) -> None:
        item: PackageItem = PackageItem(
            name="jack2-pistomp",
            installed_version="1.9.12",
            stamped_version="1.9.11",
            factory_version="1.9.10",
            available_version="1.9.13",
            last_stamp_time=datetime(2026, 6, 8, tzinfo=timezone.utc),
        )
        assert item.is_dirty is True

    def test_not_dirty_when_versions_match(self) -> None:
        item: PackageItem = PackageItem(
            name="pi-stomp",
            installed_version="2.4.1",
            stamped_version="2.4.1",
            factory_version="2.4.0",
            available_version=None,
            last_stamp_time=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )
        assert item.is_dirty is False

    def test_dirty_when_not_installed(self) -> None:
        item: PackageItem = PackageItem(
            name="pistomp-recovery",
            installed_version=None,
            stamped_version="1.0.0",
            factory_version="1.0.0",
            available_version=None,
            last_stamp_time=None,
        )
        assert item.is_dirty is True

    def test_display_right_with_update(self) -> None:
        item: PackageItem = PackageItem(
            name="mod-ui",
            installed_version="0.13.0",
            stamped_version="0.13.0",
            factory_version="0.12.0",
            available_version="0.14.0",
            last_stamp_time=datetime(2026, 6, 7, tzinfo=timezone.utc),
        )
        assert "\u2191" in item.display_right

    def test_display_right_no_update(self) -> None:
        item: PackageItem = PackageItem(
            name="pi-stomp",
            installed_version="2.4.1",
            stamped_version="2.4.1",
            factory_version="2.4.0",
            available_version=None,
            last_stamp_time=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )
        assert item.display_right == ""

    def test_version_drift(self) -> None:
        item: PackageItem = PackageItem(
            name="jack2-pistomp",
            installed_version="1.9.12",
            stamped_version="1.9.11",
            factory_version="1.9.10",
            available_version="1.9.13",
            last_stamp_time=datetime(2026, 6, 8, tzinfo=timezone.utc),
        )
        assert "1.9.12" in item.version_drift
        assert "1.9.11" in item.version_drift

    def test_version_drift_not_dirty(self) -> None:
        item: PackageItem = PackageItem(
            name="pi-stomp",
            installed_version="2.4.1",
            stamped_version="2.4.1",
            factory_version="2.4.0",
            available_version=None,
            last_stamp_time=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )
        assert item.version_drift == ""

    def test_factory_version_stored(self) -> None:
        item: PackageItem = PackageItem(
            name="mod-host-pistomp",
            installed_version="1.0.0",
            stamped_version="1.0.0",
            factory_version="0.9.0",
            available_version=None,
            last_stamp_time=None,
        )
        assert item.factory_version == "0.9.0"
