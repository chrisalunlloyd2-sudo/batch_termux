#!/usr/bin/env python3
"""
batch_termux — Real-time TUI Dashboard
Shows all sessions, resources, error history, oomph mode, and cascade status.
Refreshes every 1s. Runs in Termux terminal.
"""

import os
import sys
import json
import time
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple

BATCH_DIR = Path(os.environ.get("BATCH_DIR", str(Path.home() / ".batch_termux")))
LOG_DIR = BATCH_DIR / "logs"
SOV_DIR = Path("/root/sov")

# ── Terminal Helpers ─────────────────────────────────────────

def term_size() -> Tuple[int, int]:
    """Get terminal size (columns, rows)."""
    return shutil.get_terminal_size((80, 24))

def clear():
    """Clear screen."""
    print("\033[2J\033[H", end="")

def set_cursor(row: int, col: int = 0):
    """Move cursor to position."""
    print(f"\033[{row};{col}H", end="")

def set_color(code: str):
    """Set text color."""
    print(code, end="")

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"
BG_RED = "\033[101m"
BG_YELLOW = "\033[103m"
BG_GREEN = "\033[102m"
BG_BLUE = "\033[104m"

# ── Data Sources ─────────────────────────────────────────────

def get_resource_state() -> dict:
    """Read resource state from /proc."""
    state = {"cpu": 0.0, "mem": 0.0, "disk": 0.0, "load": "0.00 0.00 0.00"}
    
    # CPU
    try:
        with open("/proc/stat") as f:
            for line in f:
                if line.startswith("cpu "):
                    parts = line.split()
                    if len(parts) >= 5:
                        user, nice, sys_, idle = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                        total = user + nice + sys_ + idle
                        if total > 0:
                            state["cpu"] = (user + nice + sys_) / total * 100
                    break
    except: pass
    
    # Memory
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    avail_kb = int(line.split()[1])
        if total_kb > 0:
            state["mem"] = (total_kb - avail_kb) / total_kb * 100
    except: pass
    
    # Disk
    try:
        result = subprocess.run(["df", "-B1", "/data"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 4:
                total = int(parts[1])
                used = int(parts[2])
                if total > 0:
                    state["disk"] = used / total * 100
    except: pass
    
    # Load
    try:
        with open("/proc/loadavg") as f:
            state["load"] = " ".join(f.read().split()[:3])
    except: pass
    
    return state

def get_oomph_mode() -> str:
    """Read current oomph mode."""
    oomph_file = BATCH_DIR / "oomph_mode.txt"
    if oomph_file.exists():
        return oomph_file.read_text().strip()
    return "normal"

def get_error_count() -> int:
    """Count unresolved errors from error_feedback log."""
    log_file = LOG_DIR / "error_feedback.log"
    if log_file.exists():
        try:
            content = log_file.read_text()
            return content.count("ERROR") + content.count("FAILED")
        except:
            pass
    return 0

def get_cascade_results() -> List[dict]:
    """Get recent cascade results."""
    results = []
    try:
        for f in sorted(LOG_DIR.glob("cascade_*.json"), reverse=True)[:5]:
            data = json.loads(f.read_text())
            results.append(data)
    except: pass
    return results

def get_daemon_status() -> str:
    """Check if daemon is running."""
    pid_file = BATCH_DIR / "batch_daemon.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            return f"RUNNING (PID {pid})"
        except:
            return "STOPPED (stale PID)"
    return "STOPPED"

def get_sessions() -> int:
    """Count active PTY sessions."""
    socket_file = Path("/tmp/batch_termux.sock")
    if socket_file.exists():
        return 1  # Socket exists = at least 1 session
    return 0

# ── Bar Drawing ─────────────────────────────────────────────

def draw_bar(pct: float, width: int = 10) -> str:
    """Draw a colored bar."""
    filled = int(pct / 100 * width)
    filled = min(filled, width)
    empty = width - filled
    
    if pct > 90:
        color = BG_RED + WHITE
    elif pct > 80:
        color = BG_YELLOW + WHITE
    elif pct > 60:
        color = YELLOW
    else:
        color = GREEN
    
    bar = "█" * filled + "░" * empty
    return f"{color}{bar}{RESET}"

def draw_gauge(pct: float, width: int = 8) -> str:
    """Draw a compact gauge."""
    filled = int(pct / 100 * width)
    filled = min(filled, width)
    empty = width - filled
    
    if pct > 90:
        color = RED
    elif pct > 80:
        color = YELLOW
    else:
        color = GREEN
    
    return f"{color}{'●' * filled}{DIM}{'○' * empty}{RESET}"

# ── Dashboard Render ────────────────────────────────────────

def render_dashboard():
    """Render the full dashboard."""
    cols, rows = term_size()
    resources = get_resource_state()
    oomph = get_oomph_mode()
    daemon = get_daemon_status()
    errors = get_error_count()
    sessions = get_sessions()
    cascades = get_cascade_results()
    
    clear()
    row = 1
    
    # ── Header ──
    set_cursor(row, 0)
    print(f"{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════════════╗{RESET}")
    row += 1
    set_cursor(row, 0)
    print(f"{BOLD}{CYAN}║{RESET}  {WHITE}batch_termux v0.3{RESET}  {DIM}— Persistent Batch Terminal{RESET}  "
          f"{CYAN}{datetime.now().strftime('%H:%M:%S')}{RESET}  "
          f"{' ' * (cols - 70)}{CYAN}║{RESET}")
    row += 1
    set_cursor(row, 0)
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════════════════════════╝{RESET}")
    row += 2
    
    # ── Resource Panel ──
    bar_width = min(cols - 30, 20)
    
    set_cursor(row, 0)
    print(f"{BOLD}┌─ RESOURCES {'─' * (cols - 15)}┐{RESET}")
    row += 1
    
    cpu_bar = draw_bar(resources["cpu"], bar_width)
    mem_bar = draw_bar(resources["mem"], bar_width)
    disk_bar = draw_bar(resources["disk"], bar_width)
    
    set_cursor(row, 0)
    print(f"│ CPU  {cpu_bar}  {resources['cpu']:5.1f}%  "
          f"Load: {resources['load']}{' ' * (cols - 45)}│")
    row += 1
    set_cursor(row, 0)
    print(f"│ MEM  {mem_bar}  {resources['mem']:5.1f}%  "
          f"Oomph: {oomph.upper():15}{' ' * (cols - 50)}│")
    row += 1
    set_cursor(row, 0)
    print(f"│ DISK {disk_bar}  {resources['disk']:5.1f}%  "
          f"Daemon: {daemon}{' ' * (cols - 50)}│")
    row += 1
    set_cursor(row, 0)
    print(f"└{'─' * (cols - 2)}┘")
    row += 2
    
    # ── Status Panel ──
    set_cursor(row, 0)
    print(f"{BOLD}┌─ STATUS {'─' * (cols - 12)}┐{RESET}")
    row += 1
    
    status_items = [
        ("Sessions", str(sessions)),
        ("Errors", f"{RED if errors > 0 else GREEN}{errors}{RESET}"),
        ("Socket", "ACTIVE" if Path("/tmp/batch_termux.sock").exists() else "INACTIVE"),
        ("Log Dir", str(LOG_DIR)),
    ]
    
    for label, value in status_items:
        set_cursor(row, 0)
        print(f"│ {label:12s}: {value}{' ' * (cols - 20 - len(str(value)))}│")
        row += 1
    
    set_cursor(row, 0)
    print(f"└{'─' * (cols - 2)}┘")
    row += 2
    
    # ── Recent Cascades ──
    if cascades:
        set_cursor(row, 0)
        print(f"{BOLD}┌─ RECENT CASCADES {'─' * (cols - 21)}┐{RESET}")
        row += 1
        
        for c in cascades[:3]:
            status = f"{GREEN}✓ ALL PASSED{RESET}" if c.get("all_passed") else f"{RED}✗ FAILED{RESET}"
            duration = c.get("total_duration", 0)
            name = c.get("cascade_name", "unknown")
            oomph_c = c.get("oomph", "normal")
            stages = len(c.get("stages", []))
            
            set_cursor(row, 0)
            print(f"│ {status}  {name:20s}  oomph={oomph_c:12s}  "
                  f"{stages} stages  {duration:.1f}s{' ' * (cols - 65)}│")
            row += 1
        
        set_cursor(row, 0)
        print(f"└{'─' * (cols - 2)}┘")
        row += 2
    
    # ── Key Bindings ──
    set_cursor(row, 0)
    print(f"{DIM}┌─ KEYS {'─' * (cols - 10)}┐{RESET}")
    row += 1
    set_cursor(row, 0)
    print(f"{DIM}│  Ctrl+O=cycle oomph  Ctrl+S=status  Ctrl+E=errors  "
          f"Ctrl+R=retry  Ctrl+K=kill  Ctrl+H=help{' ' * (cols - 80)}│{RESET}")
    row += 1
    set_cursor(row, 0)
    print(f"{DIM}└{'─' * (cols - 2)}┘{RESET}")
    
    # ── Footer ──
    set_cursor(rows, 0)
    print(f"{DIM}Press Ctrl+C to exit dashboard{RESET}")


# ── Main Loop ───────────────────────────────────────────────

def main():
    """Run the dashboard loop."""
    try:
        # Hide cursor
        print("\033[?25l", end="")
        
        while True:
            render_dashboard()
            time.sleep(1)
            
    except KeyboardInterrupt:
        pass
    finally:
        # Show cursor
        print("\033[?25h", end="")
        clear()
        print("Dashboard closed.")


if __name__ == "__main__":
    main()
