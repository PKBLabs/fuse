#!/usr/bin/env bash
# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
#
# FUSE is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU General Public License for more details.

if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi

set -euo pipefail

APP_NAME="fuse-mod"

if [ "$(id -u)" -eq 0 ] && [ "${FUSE_ALLOW_ROOT_SETUP:-0}" != "1" ]; then
    echo "Error: do not run this setup script with sudo/root." >&2
    echo >&2
    echo "Run it as your normal user instead:" >&2
    echo "  bash fuse/scripts/setup_dev.sh" >&2
    echo >&2
    echo "If you already ran it with sudo and created a bad root venv, remove it with:" >&2
    echo "  sudo rm -rf /.venv" >&2
    exit 1
fi

FUSE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_PARENT="$(dirname "$FUSE_ROOT")"
VENV_DIR="$FUSE_ROOT/.venv"
REQUIREMENTS_FILE="$FUSE_ROOT/requirements.txt"
DEV_REQUIREMENTS_FILE="$FUSE_ROOT/requirements-dev.txt"

if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo "Error: requirements file not found: $REQUIREMENTS_FILE" >&2
    echo "Computed FUSE_ROOT: $FUSE_ROOT" >&2
    echo "Make sure you are running this from the repository checkout, for example:" >&2
    echo "  cd /home/bapage/research/fuse" >&2
    echo "  bash fuse/scripts/setup_dev.sh" >&2
    exit 1
fi

echo "FUSE root: $FUSE_ROOT"
echo "Repository parent: $REPO_PARENT"
echo

echo "Setting up Python virtual environment..."

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$REQUIREMENTS_FILE"

if [ -f "$DEV_REQUIREMENTS_FILE" ]; then
    "$VENV_DIR/bin/python" -m pip install -r "$DEV_REQUIREMENTS_FILE"
fi

echo "Initializing database..."
PYTHONPATH="$REPO_PARENT" "$VENV_DIR/bin/python" - <<'PY'
from fuse.core.persistence.db_access import ensure_database_ready

ensure_database_ready(run_plugin_bootstrap=True)
PY

mkdir -p "$HOME/.local/bin"

cat > "$HOME/.local/bin/$APP_NAME" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO_PARENT"
export PYTHONPATH="$REPO_PARENT:\${PYTHONPATH:-}"
exec "$VENV_DIR/bin/python" -m fuse.app.main "\$@"
EOF

chmod +x "$HOME/.local/bin/$APP_NAME"

echo
echo "Setup complete."
echo
echo "Run with:"
echo "  $APP_NAME"
echo
echo "If that command is not found, add this to your shell profile:"
echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""