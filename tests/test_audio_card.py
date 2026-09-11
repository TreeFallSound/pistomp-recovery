"""Tests for sound card selection preservation across a config.txt rollback."""

from __future__ import annotations

import pytest

from pistomp_recovery.audio_card import active_card, restore_config_txt

FACTORY = """\
dtparam=i2s=on

[all]
# Enable the sound card (uncomment only one)
#dtoverlay=audioinjector-wm8731-audio
dtoverlay=iqaudio-codec
#dtoverlay=hifiberry-dacplusadc

gpu_mem=16
"""


def select(text: str, card: str) -> str:
    """Return ``text`` with ``card`` the only enabled overlay."""
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        name = line.lstrip("#").strip().removeprefix("dtoverlay=")
        if line.lstrip("#").strip().startswith("dtoverlay=") and "-" in name:
            out.append(f"dtoverlay={name}\n" if name == card else f"#dtoverlay={name}\n")
        else:
            out.append(line)
    return "".join(out)


class TestActiveCard:
    def test_finds_the_enabled_card(self) -> None:
        assert active_card(FACTORY) == "iqaudio-codec"

    def test_ignores_commented_cards(self) -> None:
        assert active_card(select(FACTORY, "hifiberry-dacplusadc")) == "hifiberry-dacplusadc"

    def test_none_when_no_known_card_enabled(self) -> None:
        assert active_card(select(FACTORY, "allo-boss-dac")) is None

    def test_none_when_several_enabled(self) -> None:
        both = FACTORY.replace("#dtoverlay=hifiberry", "dtoverlay=hifiberry")
        assert active_card(both) is None

    def test_ignores_unrelated_overlays(self) -> None:
        assert active_card("dtoverlay=midi-uart0\ndtoverlay=spi0-2cs,cs0_pin=14\n") is None


class TestRestoreConfig:
    @pytest.mark.parametrize(
        "card",
        ["audioinjector-wm8731-audio", "iqaudio-codec", "hifiberry-dacplusadc"],
    )
    def test_every_supported_card_survives(self, card: str) -> None:
        merged = restore_config_txt(FACTORY, select(FACTORY, card), "factory")

        assert merged is not None
        assert active_card(merged) == card

    def test_resets_everything_but_the_card(self) -> None:
        live = select(FACTORY, "hifiberry-dacplusadc").replace("gpu_mem=16", "gpu_mem=128")

        merged = restore_config_txt(FACTORY, live, "factory")

        assert merged == select(FACTORY, "hifiberry-dacplusadc")

    def test_already_matching_selection_is_a_no_op(self) -> None:
        assert restore_config_txt(FACTORY, FACTORY, "factory") == FACTORY

    def test_declines_when_card_is_unknown(self) -> None:
        assert restore_config_txt(FACTORY, select(FACTORY, "allo-boss-dac"), "factory") is None

    def test_declines_when_restored_lacks_a_line_for_the_card(self) -> None:
        restored = FACTORY.replace("#dtoverlay=hifiberry-dacplusadc\n", "")

        assert (
            restore_config_txt(restored, select(FACTORY, "hifiberry-dacplusadc"), "factory")
            is None
        )

    def test_preserves_overlay_params_and_indentation(self) -> None:
        restored = "  dtoverlay=iqaudio-codec,foo=1\n  #dtoverlay=hifiberry-dacplusadc,bar=2\n"
        live = "  #dtoverlay=iqaudio-codec\n  dtoverlay=hifiberry-dacplusadc\n"

        merged = restore_config_txt(restored, live, "factory")

        assert (
            merged == "  #dtoverlay=iqaudio-codec,foo=1\n  dtoverlay=hifiberry-dacplusadc,bar=2\n"
        )

    def test_checkpoint_restores_the_saved_card_exactly(self) -> None:
        live = select(FACTORY, "hifiberry-dacplusadc")

        restored = restore_config_txt(FACTORY, live, "stamp")

        assert restored == FACTORY


    def test_leaves_unrelated_overlays_alone(self) -> None:
        restored = FACTORY + "dtoverlay=midi-uart0\n"
        live = select(FACTORY, "hifiberry-dacplusadc") + "#dtoverlay=midi-uart0\n"

        merged = restore_config_txt(restored, live, "factory")

        assert merged is not None
        assert merged.endswith("dtoverlay=midi-uart0\n")
        assert "#dtoverlay=midi-uart0" not in merged
