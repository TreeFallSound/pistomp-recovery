from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from enum import Enum, auto
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

from pistomp_recovery.constants import pistomp_services
from pistomp_recovery.packages.health import service_journal, service_last_result, service_status

logger = logging.getLogger(__name__)

# systemd Result values that mean the last run failed.  Result persists
# across ActiveState transitions and is only reset on a successful start.
_CRASH_RESULTS: frozenset[str] = frozenset({
    "exit-code", "signal", "core-dump", "oom-kill", "timeout",
    "protocol", "watchdog", "start-limit-hit", "resources",
    "exec-condition", "condition", "assert", "cleaning",
})


def is_crash_result(result: str) -> bool:
    """True if a systemd `Result` property indicates the last run failed."""
    return result in _CRASH_RESULTS


class BootMode(Enum):
    NORMAL = auto()
    CRASH_RECOVERY = auto()
    USER_RECOVERY = auto()


@dataclass
class CrashInfo:
    boot_mode: BootMode
    failed_service: str | None
    crash_log: str
    crash_log_full: str
    service_states: dict[str, str]
    service_results: dict[str, str] = field(default_factory=dict[str, str])


def diagnose_crash() -> CrashInfo:
    """Determine why recovery was triggered."""
    chain: list[str] = ["jack", "mod-host", "mod-ui", "mod-ala-pi-stomp"]
    return diagnose_services(chain)


def _service_crashed(state: str, result: str) -> bool:
    """True if the service last ran with a non-success Result.

    OnFailure fires immediately on a crash, but Restart=always has usually
    already moved the unit back to 'activating'/'active' by the time we look,
    so ActiveState alone misses it.  Result is reset only on a successful
    start, so it still holds the crash.
    """
    if state == "failed":
        return True
    return is_crash_result(result)


def diagnose_services(services: list[str]) -> CrashInfo:
    """Check the current health of the given services.

    Fetches both ActiveState and Result per service.  ActiveState is *now*
    (often 'activating' mid-restart after a crash); Result is *what happened
    on the last run* and only resets on a successful start, so it's the
    reliable crash signal across the OnFailure race.
    """
    states: dict[str, str] = {}
    results: dict[str, str] = {}
    failed_service: str | None = None
    for svc in services:
        state = service_status(svc)
        result = service_last_result(svc)
        states[svc] = state
        results[svc] = result
        if failed_service is None and _service_crashed(state, result):
            failed_service = svc

    crash_log: str = ""
    crash_log_full: str = ""
    if failed_service:
        # Fetch enough lines that the textarea's last-6 slice catches the
        # actual traceback even when a restart loop has filled the journal
        # with systemd's own Starting/Started lines above it.
        log = service_journal(failed_service, lines=100)
        crash_log = log
        crash_log_full = log

    boot_mode = BootMode.CRASH_RECOVERY if failed_service else BootMode.USER_RECOVERY
    return CrashInfo(
        boot_mode=boot_mode,
        failed_service=failed_service,
        crash_log=crash_log,
        crash_log_full=crash_log_full,
        service_states=states,
        service_results=results,
    )


def get_boot_mode() -> BootMode:
    return diagnose_crash().boot_mode


def stop_main_app() -> bool:
    """
    Redundant under systemd (unit Conflicts= already stops main); the safety
    net for launching recovery directly, where no conflict is enforced.
    """
    logger.info("Stopping mod-ala-pi-stomp")
    result: subprocess.CompletedProcess[str] = subprocess.run(
        ["sudo", "systemctl", "stop", "mod-ala-pi-stomp"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def start_main_app() -> bool:
    """Start the pi-Stomp service stack and let recovery exit.

    We must unload ourselves before services with `Conflicts=` can start.
    ``--no-block``just queues them: when we exit, they are unblocked.
    """
    logger.info("Resetting failure state and starting mod-ala-pi-stomp")
    all_svcs = pistomp_services()
    for svc in all_svcs:
        subprocess.run(["sudo", "systemctl", "reset-failed", svc], check=False)

    for svc in all_svcs:
        if svc == "mod-ala-pi-stomp":
            continue
        subprocess.run(["sudo", "systemctl", "start", "--no-block", svc], check=False)

    result: subprocess.CompletedProcess[str] = subprocess.run(
        ["sudo", "systemctl", "start", "--no-block", "mod-ala-pi-stomp"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def restart_jack() -> bool:
    """Restart the JACK audio server."""
    logger.info("Restarting jack")
    result: subprocess.CompletedProcess[str] = subprocess.run(
        ["sudo", "systemctl", "restart", "jack"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def restart_mod() -> bool:
    """Restart the mod-host service, which runs audio."""
    logger.info("Restarting mod-host")
    result: subprocess.CompletedProcess[str] = subprocess.run(
        ["sudo", "systemctl", "restart", "mod-host"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def recovery_sha() -> str:
    """Return a 7-char identifier for this recovery build (git sha or version)."""
    try:
        out: subprocess.CompletedProcess[str] = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except OSError:
        pass
    try:
        return _pkg_version("pistomp-recovery")[:7]
    except PackageNotFoundError:
        return "unknown"
