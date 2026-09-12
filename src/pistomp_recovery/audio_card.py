from __future__ import annotations

import re

from pistomp_recovery.constants import AUDIO_CARD_OVERLAYS

# Groups: indent, comment marker, overlay name, trailing params.
_OVERLAY_RE = re.compile(r"^(\s*)(#\s*)?dtoverlay=([A-Za-z0-9_.+-]+)(.*)$")


def card(body: str) -> str | None:
    """Return the known audio-card name selected by an overlay line."""
    match = _OVERLAY_RE.match(body)
    if match is None or match.group(3) not in AUDIO_CARD_OVERLAYS:
        return None
    return match.group(3)


def enabled(body: str) -> bool:
    """Return whether an overlay line is enabled."""
    match = _OVERLAY_RE.match(body)
    return match is not None and match.group(2) is None


def _set_enabled(body: str, on: bool) -> str:
    match = _OVERLAY_RE.match(body)
    if match is None:
        return body
    indent, name, rest = match.group(1), match.group(3), match.group(4)
    return f"{indent}{'' if on else '#'}dtoverlay={name}{rest}"


def active_card(text: str) -> str | None:
    """Return the sole enabled known audio-card overlay in ``text``.

    An absent or ambiguous selection is deliberately unknown. Factory reset
    must not guess which hardware is attached to the device.
    """
    active = [name for line in text.splitlines() if (name := card(line)) and enabled(line)]
    return active[0] if len(active) == 1 else None


def select_card(text: str, selected: str) -> str | None:
    """Apply one card selection to ``text`` while preserving all other lines.

    Returns ``None`` when ``selected`` is not a known overlay in ``text`` —
    the caller should treat that as "leave the file alone".
    """
    found = False
    lines: list[str] = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        name = card(body)
        if name is not None:
            found = found or name == selected
            body = _set_enabled(body, name == selected)
        lines.append(body + ending)
    return "".join(lines) if found else None
