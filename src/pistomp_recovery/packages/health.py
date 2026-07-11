from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)


def service_status(name: str) -> str:
    """Returns 'active', 'failed', 'inactive', etc."""
    result: subprocess.CompletedProcess[str] = subprocess.run(
        ["systemctl", "is-active", name],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def service_last_result(name: str) -> str:
    """Return the result of the last run: 'success', 'exit-code', 'signal', etc.

    Unlike ActiveState, Result is only reset when the service is *started* — not
    when it's stopped.  This lets us detect a crash even after systemd transitions
    the unit from 'failed' to 'inactive' (e.g. via Conflicts= in the recovery unit).
    """
    result: subprocess.CompletedProcess[str] = subprocess.run(
        ["systemctl", "show", name, "--property=Result", "--value"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def service_journal(name: str, lines: int = 10) -> str:
    """Returns recent journal lines for a service."""
    # sudo required: we run as `pistomp`, which cannot read /run/log/journal.
    result: subprocess.CompletedProcess[str] = subprocess.run(
        ["sudo", "journalctl", "-u", name, "-n", str(lines), "--no-pager", "--output=cat"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning("journalctl failed for %s: %s", name, result.stderr.strip())
        return ""
    return result.stdout.strip()
