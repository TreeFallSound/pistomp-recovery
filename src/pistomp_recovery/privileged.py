"""Writes to live files the recovery user may not own.

Recovery runs as ``pistomp``, but /boot/firmware (vfat, mounted root-owned)
and /var/lib/alsa belong to root. Each helper writes directly when it can and
falls back to ``sudo -n`` only when the target is not writable, so the
emulator's and tests' temp-dir roots never invoke sudo.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from pistomp_recovery.constants import SEED_SCRIPT


def _writable(path: Path) -> bool:
    return os.access(path if path.exists() else path.parent, os.W_OK)


def _sudo(*args: str, stdin: str | None = None) -> None:
    proc = subprocess.run(
        ["sudo", "-n", *args],
        input=stdin,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise OSError(f"sudo {args[0]} failed (rc={proc.returncode}): {proc.stderr.strip()}")


def write_text(path: Path, text: str) -> None:
    if _writable(path):
        path.write_text(text)
    else:
        _sudo("tee", "--", str(path), stdin=text)


def copy(src: Path, dst: Path) -> None:
    if _writable(dst):
        shutil.copy2(src, dst)
    else:
        _sudo("cp", "--preserve=timestamps", "--", str(src), str(dst))


def remove(path: Path) -> None:
    if os.access(path.parent, os.W_OK):
        path.unlink()
    else:
        _sudo("rm", "-f", "--", str(path))


def seed_alsa_state(overlay: str) -> subprocess.CompletedProcess[str]:
    """Run pistomp-audio's seed.sh, which writes the root-owned asound.state."""
    return subprocess.run(
        ["sudo", "-n", SEED_SCRIPT, overlay],
        check=False,
        capture_output=True,
        text=True,
    )
