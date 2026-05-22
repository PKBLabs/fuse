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

set -e

APP_NAME="fuse-mod"

FUSE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_PARENT="$(dirname "$FUSE_ROOT")"
VENV_DIR="$FUSE_ROOT/.venv"
REQUIREMENTS_FILE="$FUSE_ROOT/requirements.txt"

echo "Setting up Python virtual environment..."

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$REQUIREMENTS_FILE"

echo "Initializing database..."
PYTHONPATH="$REPO_PARENT" "$VENV_DIR/bin/python" - <<'PY'
from fuse.core.persistence.db_access import ensure_database_ready

ensure_database_ready(run_plugin_bootstrap=True)
PY

mkdir -p "$HOME/.local/bin"

cat > "$HOME/.local/bin/$APP_NAME" <<EOF
#!/usr/bin/env bash
set -e
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