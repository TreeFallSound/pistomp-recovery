#!/usr/bin/env bash
# Deploy pistomp-recovery source to the device via rsync and restart the service.
# Override PISTOMP_HOST / PISTOMP_USER if your device differs from the default.
set -euo pipefail

HOST="${PISTOMP_HOST:-pistomp.local}"
USER="${PISTOMP_USER:-pistomp}"
TARGET="${USER}@${HOST}"

PYTHON_VERSION="$(ssh "${TARGET}" 'python3 --version 2>&1' | grep -oE '[0-9]+\.[0-9]+')"
SITE_PACKAGES="/opt/pistomp/venvs/pistomp-recovery/lib/python${PYTHON_VERSION}/site-packages/pistomp_recovery"

echo "==> Deploying to ${TARGET} (Python ${PYTHON_VERSION})"

rsync -az --delete --exclude='__pycache__' --exclude='*.pyc' \
    src/pistomp_recovery/ \
    "${TARGET}:${SITE_PACKAGES}/"

echo "==> Restarting pistomp-recovery"
ssh "${TARGET}" 'sudo systemctl restart pistomp-recovery'

echo "==> Done"
