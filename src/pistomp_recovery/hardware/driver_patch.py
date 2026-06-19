# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportMissingImports=false
"""Monkeypatch the adafruit_rgb_display ILI9341 driver for faster transfers.

Ported from pi-stomp's ``uilib/driver_patch.py``. The upstream
``image_to_data`` (adafruit-circuitpython-rgb-display, ``adafruit_rgb_display/rgb.py``)
ends with::

    return numpy.dstack(...).flatten().tolist()

``.flatten().tolist()`` builds a Python list of ~W*H int objects (one per
pixel), then the caller wraps it in ``bytes(...)`` which walks that list again
to pack it. On a Raspberry Pi this is the single most expensive step of the
per-frame transfer path (~3.5ms for a 320x240 frame vs ~1.35ms for the
vectorised ``.tobytes()`` variant below — a 2.6x speedup). numpy is already a
hard dependency of adafruit_rgb_display, so this adds no new requirement.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_patched: bool = False


def apply() -> None:
    """Patch ``adafruit_rgb_display.rgb.image_to_data`` in place.

    Idempotent; safe to call more than once. Uses a ``__patched_by_pistomp__``
    sentinel on the target function to detect prior patches, which survives
    module reloads. No-ops if adafruit_rgb_display or numpy are unavailable.
    """
    global _patched
    if _patched:
        return

    try:
        import adafruit_rgb_display.rgb as rgb
    except ImportError:
        logger.warning("adafruit_rgb_display not found; skipping LCD driver patch")
        return

    if getattr(rgb.image_to_data, "__patched_by_pistomp__", False):
        _patched = True
        return

    try:
        import numpy
    except ImportError:
        logger.warning("numpy not found; skipping LCD driver patch")
        return

    def image_to_data_fast(image: object) -> bytes:
        data = numpy.array(image.convert("RGB")).astype("uint16")  # type: ignore[attr-defined]
        color = (
            ((data[:, :, 0] & 0xF8) << 8)
            | ((data[:, :, 1] & 0xFC) << 3)
            | (data[:, :, 2] >> 3)
        )
        packed = numpy.dstack(((color >> 8) & 0xFF, color & 0xFF)).astype(numpy.uint8)
        return packed.tobytes()

    image_to_data_fast.__patched_by_pistomp__ = True  # type: ignore[attr-defined]
    rgb.image_to_data = image_to_data_fast
    _patched = True
    logger.info("Patched adafruit_rgb_display.rgb.image_to_data (tobytes variant)")
