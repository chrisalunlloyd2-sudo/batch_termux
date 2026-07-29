#!/data/data/com.termux/files/usr/bin/bash
# batch_termux — One-shot Install
# Run: bash install.sh

set -e

BATCH_DIR="$HOME/.batch_termux"
REPO_URL="https://github.com/chrisalunlloyd2-sudo/batch_termux.git"

echo "================================================"
echo "  batch_termux — Installing..."
echo "================================================"

# ── 1. Dependencies ──
echo ""
echo "== Step 1: Dependencies =="

if ! command -v python3 &>/dev/null; then
    echo "  Installing python3..."
    pkg install -y python python-pip 2>&1 | tail -1
fi

if ! pkg list-installed 2>/dev/null | grep -q termux-api; then
    echo "  Installing termux-api..."
    pkg install -y termux-api 2>&1 | tail -1
fi

if ! command -v nc &>/dev/null; then
    echo "  Installing netcat..."
    pkg install -y netcat-openbsd 2>&1 | tail -1
fi

echo "  Installing Python packages..."
pip install regex 2>&1 | tail -1 || true

# ── 2. Directory Structure ──
echo ""
echo "== Step 2: Directory Structure =="
mkdir -p "$BATCH_DIR"/{logs,rust-core,python-cascade,hooks,config}
echo "  Created $BATCH_DIR"

# ── 3. Copy Files ──
echo ""
echo "== Step 3: Copying Files =="
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cp -r "$SCRIPT_DIR/python-cascade/"* "$BATCH_DIR/python-cascade/"
chmod +x "$BATCH_DIR/python-cascade/"*.py
echo "  Python cascade: $BATCH_DIR/python-cascade/"

cp "$SCRIPT_DIR/termux-hooks/"* "$BATCH_DIR/hooks/" 2>/dev/null || true
chmod +x "$BATCH_DIR/hooks/"*.sh 2>/dev/null || true
echo "  Termux hooks: $BATCH_DIR/hooks/"

cp -r "$SCRIPT_DIR/hooks/"* "$BATCH_DIR/config/" 2>/dev/null || true
echo "  Hook configs: $BATCH_DIR/config/"

# ── 4. Compile Rust Core ──
echo ""
echo "== Step 4: Rust Core =="
if command -v rustc &>/dev/null; then
    echo "  Compiling Rust native core..."
    cd "$SCRIPT_DIR/rust-core"
    if cargo build --release 2>&1 | tail -3; then
        cp target/release/libbatch_rust.so "$BATCH_DIR/" 2>/dev/null || true
        echo "  Rust core compiled"
    else
        echo "  Rust build failed — using Python-only mode"
    fi
    cd "$SCRIPT_DIR"
else
    echo "  Rust not available — using Python-only mode"
fi

# ── 5. Setup Termux Properties ──
echo ""
echo "== Step 5: Termux Extra Keys =="
mkdir -p "$HOME/.termux"
PROPS="$HOME/.termux/termux.properties"
if ! grep -q "batch_termux" "$PROPS" 2>/dev/null; then
    echo "" >> "$PROPS"
    echo "# batch_termux — Extra Keys" >> "$PROPS"
    echo "extra-keys = [ \\" >> "$PROPS"
    echo " ['ESC','/','-','HOME','UP','END','PGUP'], \\" >> "$PROPS"
    echo " ['TAB','CTRL','ALT','LEFT','DOWN','RIGHT','PGDN'] \\" >> "$PROPS"
    echo "]" >> "$PROPS"
    echo "  Added extra keys to $PROPS"
    termux-reload-settings 2>/dev/null || echo "  Restart Termux to apply"
else
    echo "  Extra keys already configured"
fi

# ── 6. Source in .bashrc ──
echo ""
echo "== Step 6: Shell Integration =="
BASHRC="$HOME/.bashrc"
if ! grep -q "batch_termux" "$BASHRC" 2>/dev/null; then
    echo "" >> "$BASHRC"
    echo "# batch_termux — Button hooks and daemon" >> "$BASHRC"
    echo "export BATCH_DIR=\"\$HOME/.batch_termux\"" >> "$BASHRC"
    echo "source \"\$BATCH_DIR/hooks/termux_buttons.sh\" 2>/dev/null" >> "$BASHRC"
    echo "" >> "$BASHRC"
    echo "# Auto-start daemon" >> "$BASHRC"
    echo "if [ -f \"\$BATCH_DIR/hooks/batch_daemon.sh\" ]; then" >> "$BASHRC"
    echo "    bash \"\$BATCH_DIR/hooks/batch_daemon.sh\" status | grep -q RUNNING || \\" >> "$BASHRC"
    echo "        bash \"\$BATCH_DIR/hooks/batch_daemon.sh\" start" >> "$BASHRC"
    echo "fi" >> "$BASHRC"
    echo "  Added to $BASHRC"
else
    echo "  Already in $BASHRC"
fi

# ── 7. Start Daemon ──
echo ""
echo "== Step 7: Starting Daemon =="
bash "$BATCH_DIR/hooks/batch_daemon.sh" start 2>/dev/null || true

# ── 8. Test ──
echo ""
echo "== Step 8: Quick Test =="
python3 "$BATCH_DIR/python-cascade/test_suite.py" --filter "basic" 2>&1 | tail -5 || true

echo ""
echo "================================================"
echo "  batch_termux INSTALLED"
echo "================================================"
echo "  Run: batch_button help"
echo "  Run: batch_status"
echo "  Run: batch_daemon.sh status"
echo "  Logs: $BATCH_DIR/logs/"
