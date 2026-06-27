# pyright: reportPrivateUsage=false
from __future__ import annotations

import io
import tarfile
from pathlib import Path
from typing import Any

import pytest

from pistomp_recovery import plugins
from pistomp_recovery.plugins import PluginFacet


def _make_targz(members: list[str]) -> bytes:
    """Build an in-memory .tar.gz with one tiny file per member path."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name in members:
            data = b"# ttl\n"
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class _FakeResp:
    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)
        self.headers = {"Content-Length": str(len(data))}

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)


def _noop_progress(label: str, frac: float, detail: str, done: bool) -> None:
    pass


def _patch_download(monkeypatch: pytest.MonkeyPatch, data: bytes) -> None:
    def fake_urlopen(url: Any, timeout: Any = None) -> _FakeResp:
        return _FakeResp(data)

    monkeypatch.setattr(plugins.urllib.request, "urlopen", fake_urlopen)


def test_system_plugin_bundles_reads_recorded_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The recorded builder list is the authoritative exclusion set."""
    listfile = tmp_path / "factory-lv2-system-bundles.list"
    listfile.write_text("cabsim.lv2\nsfizz.lv2\n# comment\n\n")
    monkeypatch.setattr(plugins, "FACTORY_LV2_SYSTEM_BUNDLES_FILE", str(listfile))

    facet = PluginFacet(path=tmp_path / ".lv2")
    assert facet._system_plugin_bundles() == {"cabsim.lv2", "sfizz.lv2"}


def test_reset_excludes_package_delivered_bundles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A factory reset must not re-extract a package-delivered bundle, but
    must restore tarball-delivered ones."""
    listfile = tmp_path / "factory-lv2-system-bundles.list"
    listfile.write_text("cabsim.lv2\n")
    monkeypatch.setattr(plugins, "FACTORY_LV2_SYSTEM_BUNDLES_FILE", str(listfile))

    _patch_download(
        monkeypatch,
        _make_targz(
            [
                ".lv2/cabsim.lv2/manifest.ttl",
                ".lv2/cabsim.lv2/modgui/icon.png",
                ".lv2/gx_amp.lv2/manifest.ttl",
            ]
        ),
    )

    facet = PluginFacet(path=tmp_path / ".lv2")
    assert facet.reset_factory_plugins(_noop_progress) is True

    lv2 = tmp_path / ".lv2"
    assert (lv2 / "gx_amp.lv2" / "manifest.ttl").is_file()  # tarball plugin restored
    assert not (lv2 / "cabsim.lv2").exists()  # package plugin not shadowed


def test_reset_extracts_all_when_no_exclusions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No recorded list (older image) → nothing excluded, plain additive extract."""
    monkeypatch.setattr(plugins, "FACTORY_LV2_SYSTEM_BUNDLES_FILE", str(tmp_path / "missing.list"))

    _patch_download(
        monkeypatch,
        _make_targz([".lv2/cabsim.lv2/manifest.ttl", ".lv2/gx_amp.lv2/manifest.ttl"]),
    )

    facet = PluginFacet(path=tmp_path / ".lv2")
    assert facet.reset_factory_plugins(_noop_progress) is True

    lv2 = tmp_path / ".lv2"
    assert (lv2 / "cabsim.lv2" / "manifest.ttl").is_file()
    assert (lv2 / "gx_amp.lv2" / "manifest.ttl").is_file()


def test_system_plugin_bundles_empty_when_no_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing recorded list → empty set (no crash, no exclusions)."""
    monkeypatch.setattr(plugins, "FACTORY_LV2_SYSTEM_BUNDLES_FILE", str(tmp_path / "missing.list"))
    facet = PluginFacet(path=tmp_path / ".lv2")
    assert facet._system_plugin_bundles() == set()
