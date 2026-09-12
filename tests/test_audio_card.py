"""Tests for reading and rewriting the audio-card selection in config.txt."""

from __future__ import annotations

import pytest

from pistomp_recovery.audio_card import active_card, select_card

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


class TestSelectCard:
    @pytest.mark.parametrize(
        "card",
        ["audioinjector-wm8731-audio", "iqaudio-codec", "hifiberry-dacplusadc"],
    )
    def test_every_supported_card_can_be_selected(self, card: str) -> None:
        selected = select_card(FACTORY, card)

        assert selected is not None
        assert active_card(selected) == card

    def test_changes_nothing_but_the_card(self) -> None:
        assert select_card(FACTORY, "hifiberry-dacplusadc") == select(
            FACTORY, "hifiberry-dacplusadc"
        )

    def test_already_selected_card_is_a_no_op(self) -> None:
        assert select_card(FACTORY, "iqaudio-codec") == FACTORY

    def test_declines_when_the_text_has_no_line_for_the_card(self) -> None:
        without = FACTORY.replace("#dtoverlay=hifiberry-dacplusadc\n", "")

        assert select_card(without, "hifiberry-dacplusadc") is None

    def test_preserves_overlay_params_and_indentation(self) -> None:
        text = "  dtoverlay=iqaudio-codec,foo=1\n  #dtoverlay=hifiberry-dacplusadc,bar=2\n"

        assert select_card(text, "hifiberry-dacplusadc") == (
            "  #dtoverlay=iqaudio-codec,foo=1\n  dtoverlay=hifiberry-dacplusadc,bar=2\n"
        )

    def test_leaves_unrelated_overlays_alone(self) -> None:
        selected = select_card(FACTORY + "dtoverlay=midi-uart0\n", "hifiberry-dacplusadc")

        assert selected is not None
        assert selected.endswith("dtoverlay=midi-uart0\n")
        assert "#dtoverlay=midi-uart0" not in selected
