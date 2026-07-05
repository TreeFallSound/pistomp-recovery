# pyright: reportPrivateUsage=false
"""Tests for boot-mode detection and crash diagnosis."""

from __future__ import annotations

from unittest.mock import patch

from pistomp_recovery.service import (
    BootMode,
    _service_crashed,
    diagnose_services,
    get_boot_mode,
    is_crash_result,
)

# ---------------------------------------------------------------------------
# is_crash_result
# ---------------------------------------------------------------------------


def test_is_crash_result_recognises_exit_code() -> None:
    assert is_crash_result("exit-code") is True


def test_is_crash_result_recognises_signal() -> None:
    assert is_crash_result("signal") is True


def test_is_crash_result_rejects_success() -> None:
    assert is_crash_result("success") is False


def test_is_crash_result_rejects_empty() -> None:
    assert is_crash_result("") is False


# ---------------------------------------------------------------------------
# _service_crashed
# ---------------------------------------------------------------------------


def test_service_crashed_failed_state() -> None:
    """ActiveState=failed is always a crash regardless of Result."""
    assert _service_crashed("failed", "success") is True


def test_service_crashed_inactive_with_bad_result() -> None:
    """ActiveState=inactive + Result=exit-code means Conflicts= cleared a failed unit."""
    assert _service_crashed("inactive", "exit-code") is True


def test_service_crashed_inactive_with_signal() -> None:
    assert _service_crashed("inactive", "signal") is True


def test_service_crashed_inactive_clean_stop() -> None:
    """ActiveState=inactive + Result=success means a clean stop, not a crash."""
    assert _service_crashed("inactive", "success") is False


def test_service_crashed_inactive_no_result() -> None:
    """ActiveState=inactive + empty Result means service never ran."""
    assert _service_crashed("inactive", "") is False


def test_service_crashed_active() -> None:
    assert _service_crashed("active", "success") is False


def test_service_crashed_activating_with_exit_code() -> None:
    """The OnFailure race: Restart=always has moved the unit back to
    'activating' but Result still holds 'exit-code' from the crash."""
    assert _service_crashed("activating", "exit-code") is True


def test_service_crashed_active_with_exit_code() -> None:
    """Same race but systemd has already re-entered 'active' on a fast restart."""
    assert _service_crashed("active", "exit-code") is True


def test_service_crashed_activating_with_signal() -> None:
    assert _service_crashed("activating", "signal") is True


def test_service_crashed_activating_clean() -> None:
    """A genuinely booting service (no prior crash) is not a crash."""
    assert _service_crashed("activating", "success") is False


# ---------------------------------------------------------------------------
# diagnose_services
# ---------------------------------------------------------------------------


def test_diagnose_services_picks_first_failed() -> None:
    """The most foundational (earliest in the chain) failed service is reported."""
    with (
        patch("pistomp_recovery.service.service_status") as mock_status,
        patch("pistomp_recovery.service.service_last_result", return_value="exit-code"),
        patch("pistomp_recovery.service.service_journal", return_value="audio: no card"),
    ):
        def _status(svc: str) -> str:
            return "failed" if svc == "jack" else "inactive"

        mock_status.side_effect = _status
        info = diagnose_services(["jack", "mod-host", "mod-ui", "mod-ala-pi-stomp"])

    assert info.boot_mode == BootMode.CRASH_RECOVERY
    assert info.failed_service == "jack"
    assert info.service_states["mod-host"] == "inactive"
    assert info.service_results["jack"] == "exit-code"
    assert info.service_results["mod-host"] == "exit-code"


def test_diagnose_services_detects_crash_via_result() -> None:
    """Crash is detected even when Conflicts= has already cleared ActiveState to inactive."""

    def _status(svc: str) -> str:
        return "inactive"  # Conflicts= stopped everything

    def _result(svc: str) -> str:
        return "exit-code" if svc == "mod-ala-pi-stomp" else "success"

    with (
        patch("pistomp_recovery.service.service_status", side_effect=_status),
        patch("pistomp_recovery.service.service_last_result", side_effect=_result),
        patch("pistomp_recovery.service.service_journal", return_value=""),
    ):
        info = diagnose_services(["jack", "mod-host", "mod-ui", "mod-ala-pi-stomp"])

    assert info.boot_mode == BootMode.CRASH_RECOVERY
    assert info.failed_service == "mod-ala-pi-stomp"


def test_diagnose_services_no_crash() -> None:
    """All services active → USER_RECOVERY, no failed service."""
    with (
        patch("pistomp_recovery.service.service_status", return_value="active"),
        patch("pistomp_recovery.service.service_last_result", return_value="success"),
    ):
        info = diagnose_services(["jack", "mod-host", "mod-ui", "mod-ala-pi-stomp"])

    assert info.boot_mode == BootMode.USER_RECOVERY
    assert info.failed_service is None


def test_diagnose_services_detects_onfailure_race() -> None:
    """The real-world OnFailure race: mod-ala-pi-stomp is back in 'activating'
    (Restart=always already queued the next attempt) but Result='exit-code'
    still holds from the crash that triggered OnFailure=recovery."""
    def _status(svc: str) -> str:
        if svc == "mod-ala-pi-stomp":
            return "activating"
        return "active"

    def _result(svc: str) -> str:
        return "exit-code" if svc == "mod-ala-pi-stomp" else "success"

    with (
        patch("pistomp_recovery.service.service_status", side_effect=_status),
        patch("pistomp_recovery.service.service_last_result", side_effect=_result),
        patch("pistomp_recovery.service.service_journal", return_value="Traceback ..."),
    ):
        info = diagnose_services(["jack", "mod-host", "mod-ui", "mod-ala-pi-stomp"])

    assert info.boot_mode == BootMode.CRASH_RECOVERY
    assert info.failed_service == "mod-ala-pi-stomp"
    assert info.crash_log == "Traceback ..."
    assert info.service_states["mod-ala-pi-stomp"] == "activating"
    assert info.service_results["mod-ala-pi-stomp"] == "exit-code"
    assert info.service_results["jack"] == "success"


def test_diagnose_services_activating_race_surfaces_as_crashed() -> None:
    """The classic crash-loop shape: jack is up, mod-host crashed and is back
    to 'activating' under Restart=always, mod-ui/pi-stomp are inactive waits.
    The first crashed service in the chain (mod-host) is reported, and its
    Result is captured in service_results so the UI can show 'crashed' instead
    of the misleading 'activating' ActiveState."""
    def _status(svc: str) -> str:
        if svc == "jack":
            return "active"
        if svc == "mod-host":
            return "activating"
        return "inactive"

    def _result(svc: str) -> str:
        if svc == "mod-host":
            return "exit-code"
        return "success"

    with (
        patch("pistomp_recovery.service.service_status", side_effect=_status),
        patch("pistomp_recovery.service.service_last_result", side_effect=_result),
        patch("pistomp_recovery.service.service_journal", return_value="jack backend gone"),
    ):
        info = diagnose_services(["jack", "mod-host", "mod-ui", "mod-ala-pi-stomp"])

    assert info.boot_mode == BootMode.CRASH_RECOVERY
    assert info.failed_service == "mod-host"
    assert info.service_states["mod-host"] == "activating"
    assert info.service_results["mod-host"] == "exit-code"
    assert info.service_results["jack"] == "success"
    assert info.service_results["mod-ui"] == "success"
    assert info.crash_log == "jack backend gone"


def test_get_boot_mode_crash_when_jack_stopped_after_crash() -> None:
    """get_boot_mode returns CRASH_RECOVERY even if jack is only 'inactive' post-crash."""
    with (
        patch("pistomp_recovery.service.service_status", return_value="inactive"),
        patch("pistomp_recovery.service.service_last_result") as mock_result,
        patch("pistomp_recovery.service.service_journal", return_value=""),
    ):
        def _result(svc: str) -> str:
            return "exit-code" if svc == "jack" else "success"

        mock_result.side_effect = _result
        assert get_boot_mode() == BootMode.CRASH_RECOVERY


def test_get_boot_mode_user_recovery_when_all_clean() -> None:
    with (
        patch("pistomp_recovery.service.service_status", return_value="inactive"),
        patch("pistomp_recovery.service.service_last_result", return_value="success"),
    ):
        assert get_boot_mode() == BootMode.USER_RECOVERY
