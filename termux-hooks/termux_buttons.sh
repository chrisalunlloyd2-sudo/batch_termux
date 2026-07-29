#!/data/data/com.termux/files/usr/bin/bash
# batch_termux — Termux Button Hooks
# Wires all Termux extra keys to batch commands
# Source this in ~/.bashrc or ~/.zshrc

BATCH_DIR="${BATCH_DIR:-$HOME/.batch_termux}"
BATCH_LOG="$BATCH_DIR/logs/buttons.log"
BATCH_SOCKET="${BATCH_SOCKET:-/tmp/batch_termux.sock}"

mkdir -p "$BATCH_DIR/logs"

# ── Button Bindings ──────────────────────────────────────────
# These map to Termux extra keys (Volume Up/Down + key combos)

batch_button_help() {
    echo "╔══════════════════════════════════════════════╗"
    echo "║  batch_termux — Button Bindings             ║"
    echo "╠══════════════════════════════════════════════╣"
    echo "║  Ctrl+Shift+B  — Run current batch script   ║"
    echo "║  Ctrl+Shift+T  — Run test suite             ║"
    echo "║  Ctrl+Shift+C  — Run cascade                 ║"
    echo "║  Ctrl+Shift+S  — Show resource status        ║"
    echo "║  Ctrl+Shift+E  — Show error history          ║"
    echo "║  Ctrl+Shift+R  — Retry last failed command   ║"
    echo "║  Ctrl+Shift+K  — Kill stuck process          ║"
    echo "║  Ctrl+Shift+Q  — Quit batch daemon           ║"
    echo "║  Ctrl+Shift+H  — This help                   ║"
    echo "╚══════════════════════════════════════════════╝"
}

# ── Batch Command Queue ─────────────────────────────────────

batch_queue() {
    local cmd="$*"
    echo "[$(date +%H:%M:%S)] QUEUE: $cmd" >> "$BATCH_LOG"
    
    # Send to Rust daemon via socket if available
    if [ -S "$BATCH_SOCKET" ]; then
        echo "$cmd" | nc -q0 -U "$BATCH_SOCKET" 2>/dev/null
        return $?
    fi
    
    # Fallback: run directly
    echo "Running: $cmd"
    eval "$cmd"
}

# ── Resource Monitor ─────────────────────────────────────────

batch_status() {
    echo "╔══════════════════════════════════════════════╗"
    echo "║  batch_termux — Resource Status             ║"
    echo "╠══════════════════════════════════════════════╣"
    
    # CPU
    if [ -f /proc/stat ]; then
        local cpu_line=$(grep '^cpu ' /proc/stat)
        local cpu_user=$(echo "$cpu_line" | awk '{print $2}')
        local cpu_nice=$(echo "$cpu_line" | awk '{print $3}')
        local cpu_sys=$(echo "$cpu_line" | awk '{print $4}')
        local cpu_idle=$(echo "$cpu_line" | awk '{print $5}')
        local cpu_total=$((cpu_user + cpu_nice + cpu_sys + cpu_idle))
        local cpu_used=$((cpu_user + cpu_nice + cpu_sys))
        if [ "$cpu_total" -gt 0 ]; then
            local cpu_pct=$((cpu_used * 100 / cpu_total))
            printf "║  CPU:  %3d%%  %s║\n" "$cpu_pct" "$(batch_bar $cpu_pct 10)"
        fi
    fi
    
    # Memory
    if [ -f /proc/meminfo ]; then
        local mem_total=$(grep 'MemTotal:' /proc/meminfo | awk '{print $2}')
        local mem_avail=$(grep 'MemAvailable:' /proc/meminfo | awk '{print $2}')
        if [ -n "$mem_total" ] && [ "$mem_total" -gt 0 ]; then
            local mem_used=$((mem_total - mem_avail))
            local mem_pct=$((mem_used * 100 / mem_total))
            printf "║  MEM:  %3d%%  %s║\n" "$mem_pct" "$(batch_bar $mem_pct 10)"
        fi
    fi
    
    # Disk
    local disk_info=$(df -B1 /data 2>/dev/null | tail -1)
    if [ -n "$disk_info" ]; then
        local disk_total=$(echo "$disk_info" | awk '{print $2}')
        local disk_used=$(echo "$disk_info" | awk '{print $3}')
        if [ -n "$disk_total" ] && [ "$disk_total" -gt 0 ]; then
            local disk_pct=$((disk_used * 100 / disk_total))
            printf "║  DISK: %3d%%  %s║\n" "$disk_pct" "$(batch_bar $disk_pct 10)"
        fi
    fi
    
    # Load average
    if [ -f /proc/loadavg ]; then
        local load=$(cat /proc/loadavg | awk '{print $1, $2, $3}')
        printf "║  LOAD: %s║\n" "$load"
    fi
    
    echo "╚══════════════════════════════════════════════╝"
}

batch_bar() {
    local pct=$1
    local segments=$2
    local filled=$((pct * segments / 100))
    local empty=$((segments - filled))
    local bar=""
    for ((i=0; i<filled; i++)); do bar="${bar}█"; done
    for ((i=0; i<empty; i++)); do bar="${bar}░"; done
    echo "$bar"
}

# ── Error History ─────────────────────────────────────────────

batch_errors() {
    local logfile="$BATCH_DIR/logs/error_feedback.log"
    if [ -f "$logfile" ]; then
        echo "╔══════════════════════════════════════════════╗"
        echo "║  Recent Errors (last 10)                   ║"
        echo "╠══════════════════════════════════════════════╣"
        tail -10 "$logfile" | while read line; do
            echo "║  $line"
        done
        echo "╚══════════════════════════════════════════════╝"
    else
        echo "No error log found."
    fi
}

# ── Last Command Retry ──────────────────────────────────────

batch_retry() {
    local last_cmd_file="$BATCH_DIR/last_command.txt"
    if [ -f "$last_cmd_file" ]; then
        local last_cmd=$(cat "$last_cmd_file")
        echo "Retrying: $last_cmd"
        eval "$last_cmd"
    else
        echo "No previous command to retry."
    fi
}

# ── Kill Stuck Process ──────────────────────────────────────

batch_kill() {
    echo "Finding stuck processes..."
    ps aux | grep -E "batch|python3.*cascade|python3.*test" | grep -v grep
    echo ""
    read -p "Kill all batch processes? (y/N): " confirm
    if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
        pkill -f "batch_termux" 2>/dev/null
        pkill -f "python3.*cascade" 2>/dev/null
        pkill -f "python3.*test_suite" 2>/dev/null
        echo "Done."
    fi
}

# ── Key Bindings (for ~/.termux/termux.properties) ──────────

batch_setup_keys() {
    local props="$HOME/.termux/termux.properties"
    mkdir -p "$HOME/.termux"
    
    if [ ! -f "$props" ]; then
        cat > "$props" << 'PROPSEOF'
# batch_termux — Extra Keys Configuration
extra-keys = [ \
 ['ESC','/','-','HOME','UP','END','PGUP'], \
 ['TAB','CTRL','ALT','LEFT','DOWN','RIGHT','PGDN'] \
]
PROPSEOF
        echo "Created $props"
        echo "Restart Termux or run: termux-reload-settings"
    else
        echo "$props already exists. Edit manually to add batch keys."
    fi
}

# ── Main Dispatch ────────────────────────────────────────────

batch_button() {
    local action="${1:-help}"
    shift 2>/dev/null
    
    case "$action" in
        help|h|-h|--help)
            batch_button_help
            ;;
        status|s)
            batch_status
            ;;
        errors|e)
            batch_errors
            ;;
        retry|r)
            batch_retry
            ;;
        kill|k)
            batch_kill
            ;;
        queue|q)
            batch_queue "$@"
            ;;
        setup-keys)
            batch_setup_keys
            ;;
        *)
            echo "Unknown action: $action"
            batch_button_help
            ;;
    esac
}

# ── Auto-source in .bashrc ──────────────────────────────────

# If sourced directly, show help
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    batch_button "$@"
fi
