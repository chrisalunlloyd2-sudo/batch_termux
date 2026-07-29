#!/data/data/com.termux/files/usr/bin/bash
# batch_termux — Persistent Background Daemon
# v0.3 — Dashboard support, oomph-aware, auto-restart

BATCH_DIR="${BATCH_DIR:-$HOME/.batch_termux}"
BATCH_PID_FILE="$BATCH_DIR/batch_daemon.pid"
BATCH_LOG="$BATCH_DIR/logs/daemon.log"
BATCH_SOCKET="${BATCH_SOCKET:-/tmp/batch_termux.sock}"

mkdir -p "$BATCH_DIR/logs"

daemon_start() {
    if [ -f "$BATCH_PID_FILE" ]; then
        local old_pid=$(cat "$BATCH_PID_FILE")
        if kill -0 "$old_pid" 2>/dev/null; then
            echo "batch_termux daemon already running (PID $old_pid)"
            return 1
        fi
        rm -f "$BATCH_PID_FILE"
    fi
    
    echo "Starting batch_termux daemon..."
    
    # Read oomph mode
    local oomph="normal"
    if [ -f "$BATCH_DIR/oomph_mode.txt" ]; then
        oomph=$(cat "$BATCH_DIR/oomph_mode.txt")
    fi
    echo "  Oomph mode: $oomph"
    
    # Start Python daemon
    nohup python3 -c "
import sys, time, json, subprocess, logging, os, socket

sys.path.insert(0, '$BATCH_DIR/python-cascade')
from cascade import AutomationCascade, CascadeStage
from error_feedback import ErrorFeedbackEngine

logging.basicConfig(filename='$BATCH_LOG', level=logging.INFO,
    format='%(asctime)s [DAEMON] %(message)s')
log = logging.getLogger('daemon')

log.info('batch_termux daemon started (oomph=$oomph)')
engine = ErrorFeedbackEngine()

# Read oomph mode
oomph_file = '$BATCH_DIR/oomph_mode.txt'
oomph = '$oomph'

# Unix socket
try:
    os.unlink('$BATCH_SOCKET')
except: pass

server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind('$BATCH_SOCKET')
server.listen(5)
server.settimeout(1.0)

log.info('Listening on $BATCH_SOCKET')

while True:
    try:
        conn, addr = server.accept()
        data = conn.recv(4096).decode().strip()
        
        if data.startswith('oomph:'):
            # Oomph mode change
            oomph = data[6:]
            with open(oomph_file, 'w') as f:
                f.write(oomph)
            log.info(f'Oomph changed to: {oomph}')
            conn.sendall(json.dumps({'status': 'ok', 'oomph': oomph}).encode())
        elif data == 'status':
            # Status request
            status = {
                'oomph': oomph,
                'uptime': time.time(),
                'errors': engine.unresolved_count(),
                'pid': os.getpid(),
            }
            conn.sendall(json.dumps(status).encode())
        elif data:
            # Command execution
            log.info(f'Received: {data[:80]}')
            result = subprocess.run(data, shell=True, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                fix = engine.process(data, result.stdout, result.stderr, [])
                if fix:
                    log.info(f'Retrying with fix: {fix[:80]}')
                    result = subprocess.run(fix, shell=True, capture_output=True, text=True, timeout=60)
            conn.sendall(json.dumps({
                'exit': result.returncode,
                'stdout': result.stdout[:1000],
                'stderr': result.stderr[:500],
            }).encode())
        conn.close()
    except socket.timeout:
        continue
    except Exception as e:
        log.error(f'Error: {e}')
        time.sleep(1)
" > "$BATCH_DIR/logs/daemon_stdout.log" 2>&1 &
    
    local pid=$!
    echo "$pid" > "$BATCH_PID_FILE"
    echo "batch_termux daemon started (PID $pid)"
    echo "  Socket: $BATCH_SOCKET"
    echo "  Oomph:  $oomph"
    echo "  Log:    $BATCH_LOG"
}

daemon_stop() {
    if [ -f "$BATCH_PID_FILE" ]; then
        local pid=$(cat "$BATCH_PID_FILE")
        kill "$pid" 2>/dev/null
        rm -f "$BATCH_PID_FILE"
        rm -f "$BATCH_SOCKET"
        echo "batch_termux daemon stopped"
    else
        echo "No daemon running"
    fi
}

daemon_status() {
    if [ -f "$BATCH_PID_FILE" ]; then
        local pid=$(cat "$BATCH_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            local oomph="normal"
            [ -f "$BATCH_DIR/oomph_mode.txt" ] && oomph=$(cat "$BATCH_DIR/oomph_mode.txt")
            echo "batch_termux daemon: RUNNING (PID $pid)"
            echo "  Oomph:  $oomph"
            echo "  Uptime: $(ps -o etime= -p $pid 2>/dev/null | tr -d ' ')"
            echo "  Memory: $(ps -o rss= -p $pid 2>/dev/null | tr -d ' ') KB"
            echo "  Socket: $BATCH_SOCKET"
        else
            echo "batch_termux daemon: STOPPED (stale PID file)"
            rm -f "$BATCH_PID_FILE"
        fi
    else
        echo "batch_termux daemon: STOPPED"
    fi
}

daemon_restart() {
    daemon_stop
    sleep 1
    daemon_start
}

case "${1:-status}" in
    start)   daemon_start ;;
    stop)    daemon_stop ;;
    restart) daemon_restart ;;
    status)  daemon_status ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
