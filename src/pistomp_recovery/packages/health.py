from __future__ import annotations

import logging
import socket
import subprocess
import time

logger = logging.getLogger(__name__)

JACK_CHECK_TIMEOUT: float = 10.0
MOD_HOST_CHECK_TIMEOUT: float = 30.0
MOD_UI_CHECK_TIMEOUT: float = 30.0
PISTOMP_CHECK_TIMEOUT: float = 60.0
HEALTH_STAMP_FILE: str = "/run/pistomp-healthy"


def check_jack(timeout: float = JACK_CHECK_TIMEOUT) -> bool:
    start: float = time.monotonic()
    while time.monotonic() - start < timeout:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["jack_lsp"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.info("JACK health check passed")
            return True
        time.sleep(0.5)
    logger.error("JACK health check timed out after %.1fs", timeout)
    return False


def check_port(host: str, port: int, timeout: float) -> bool:
    start: float = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            sock: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect((host, port))
            sock.close()
            return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return False


def check_mod_host(timeout: float = MOD_HOST_CHECK_TIMEOUT) -> bool:
    logger.info("Checking mod-host on port 5555...")
    result: bool = check_port("127.0.0.1", 5555, timeout)
    if result:
        logger.info("mod-host health check passed")
    else:
        logger.error("mod-host health check timed out")
    return result


def check_mod_ui(timeout: float = MOD_UI_CHECK_TIMEOUT) -> bool:
    logger.info("Checking mod-ui on port 80...")
    result: bool = check_port("127.0.0.1", 80, timeout)
    if result:
        logger.info("mod-ui health check passed")
    else:
        logger.error("mod-ui health check timed out")
    return result


def check_pistomp_healthy(timeout: float = PISTOMP_CHECK_TIMEOUT) -> bool:
    import os
    start: float = time.monotonic()
    while time.monotonic() - start < timeout:
        if os.path.exists(HEALTH_STAMP_FILE):
            logger.info("pi-stomp health stamp found")
            return True
        time.sleep(1.0)
    logger.error("pi-stomp health check timed out after %.1fs", timeout)
    return False


def full_health_check() -> dict[str, bool]:
    results: dict[str, bool] = {}
    logger.info("Starting full health check...")

    subprocess.run(["systemctl", "start", "jack"], check=False)
    results["jack"] = check_jack()
    if not results["jack"]:
        return results

    subprocess.run(["systemctl", "start", "mod-host"], check=False)
    results["mod_host"] = check_mod_host()
    if not results["mod_host"]:
        return results

    subprocess.run(["systemctl", "start", "mod-ui"], check=False)
    results["mod_ui"] = check_mod_ui()

    subprocess.run(["systemctl", "reset-failed", "mod-ala-pi-stomp"], check=False)
    subprocess.run(["systemctl", "start", "mod-ala-pi-stomp"], check=False)
    results["pistomp"] = check_pistomp_healthy()

    return results
