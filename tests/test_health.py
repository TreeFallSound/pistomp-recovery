"""Tests for service health probes."""

from __future__ import annotations

import subprocess
from typing import Any
from unittest.mock import patch

import pytest

from pistomp_recovery.packages.health import service_journal

_PERMISSION_ERROR: str = "No journal files were opened due to insufficient permissions."


def _completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_service_journal_runs_under_sudo() -> None:
    """`pistomp` cannot read /run/log/journal, so the read must be privileged."""
    with patch("subprocess.run", return_value=_completed(stdout="boom\n")) as mock_run:
        service_journal("jack", lines=5)

    argv: list[str] = mock_run.call_args.args[0]
    assert argv[0] == "sudo"
    assert argv[1] == "journalctl"
    assert "jack" in argv


def test_service_journal_returns_log_lines() -> None:
    with patch("subprocess.run", return_value=_completed(stdout="Unknown PCM hw:0\n")):
        assert service_journal("jack") == "Unknown PCM hw:0"


def test_service_journal_returns_empty_when_journalctl_fails() -> None:
    """A permissions failure writes to stderr and leaves stdout empty."""
    with patch("subprocess.run", return_value=_completed(returncode=1, stderr=_PERMISSION_ERROR)):
        assert service_journal("jack") == ""


def test_service_journal_logs_stderr_on_failure(caplog: pytest.LogCaptureFixture) -> None:
    """The failure must be visible; silently swallowing it is the bug we fixed."""
    with patch("subprocess.run", return_value=_completed(returncode=1, stderr=_PERMISSION_ERROR)):
        with caplog.at_level("WARNING"):
            service_journal("jack")

    assert _PERMISSION_ERROR in caplog.text


def test_service_journal_does_not_return_stdout_on_failure() -> None:
    """Never surface partial stdout from a failed read as if it were the log."""
    with patch(
        "subprocess.run",
        return_value=_completed(returncode=1, stdout="partial", stderr=_PERMISSION_ERROR),
    ):
        assert service_journal("jack") == ""


@pytest.mark.parametrize("lines", [1, 10, 100])
def test_service_journal_passes_line_count(lines: int) -> None:
    with patch("subprocess.run", return_value=_completed(stdout="x")) as mock_run:
        service_journal("jack", lines=lines)

    argv: list[Any] = mock_run.call_args.args[0]
    assert str(lines) in argv
