#!/usr/bin/env bash
set -e

APP_NAME="fuse-mod"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "Setting up Python virtual environment..."

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo "Initializing database..."
.venv/bin/python initialize_db.py

mkdir -p "$HOME/.local/bin"

cat > "$HOME/.local/bin/$APP_NAME" <<EOF
#!/usr/bin/env bash
set -e

if [ -f "\$HOME/.bashrc" ]; then
    source "\$HOME/.bashrc"
fi

cd "$PROJECT_ROOT"
exec "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/main.py" "\$@"
EOF

chmod +x "$HOME/.local/bin/$APP_NAME"

echo
echo "Setup complete."
echo
echo "Run with:"
echo "  $APP_NAME"