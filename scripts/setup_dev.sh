#!/usr/bin/env bash
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "Setting up Python virtual environment..."

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .

echo "Initializing database..."
.venv/bin/python initialize_db.py

echo
echo "Setup complete."
echo
echo "Run with:"
echo "  source .venv/bin/activate"
echo "  fuse-mod"

mkdir -p "$HOME/.local/bin"

cat > "$HOME/.local/bin/fuse-mod" <<EOF
#!/usr/bin/env bash
set -e

source ~/.bashrc
cd "$PROJECT_ROOT"
exec "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/main.py" "\$@"
EOF

chmod +x "$HOME/.local/bin/fuse-mod"
