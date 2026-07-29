# batch_termux

**Persistent batch terminal for Termux** — Rust native core with psutil monitoring, regex hooks, error recursion feedback, and resource pressure pacing.

Bridges nova-terminal's Rust heartbeat pacer (50ms tick) with sims1337/matrixwince's agent infrastructure. Every button in Termux gets a batch hook. Every automation cascade gets a headless test suite. Every error feeds back into the model.

## Architecture

```
batch_termux/
├── src/                    # Rust native core (libbatch_rust.so)
│   ├── main.rs            # Entry point, heartbeat pacer
│   ├── pacer.rs           # 50ms tick scheduler
│   ├── batch.rs           # Batch command queue & execution
│   ├── monitor.rs         # psutil-style resource monitoring
│   ├── hooks.rs           # Regex-based hook engine
│   ├── error_recursion.rs # Error capture → feedback loop
│   └── display.rs         # Resource pressure display
├── python/                 # Python automation layer
│   ├── cascade.py         # Headless automation cascade
│   ├── test_suite.py      # Headless testing suite
│   ├── model_pacer.py     # Model pacing hooks
│   └── error_feedback.py  # Error recursion → model feedback
├── scripts/                # Termux integration
│   ├── termux_buttons.sh  # Hook all Termux buttons
│   ├── install.sh         # One-shot install
│   └── batch_daemon.sh   # Persistent background daemon
├── hooks/                  # Pre-built regex hooks
│   ├── compile.json       # Compile error patterns
│   ├── oom.json           # OOM detection patterns
│   └── crash.json         # Crash recovery patterns
├── tests/                  # Test suite
│   └── test_cascade.py    # Cascade tests
└── Cargo.toml             # Rust project
```

## Quick Install

```bash
git clone https://github.com/chrisalunlloyd2-sudo/batch_termux
cd batch_termux
bash scripts/install.sh
```

## Core Features

### 1. Persistent Batch Terminal
- 50ms heartbeat pacer (from nova-terminal)
- Batch command queue with priority levels
- Persistent across shell restarts
- All Termux buttons wired to batch hooks

### 2. Resource Monitoring (psutil-style)
- CPU usage per core + aggregate
- Memory pressure (RAM + swap)
- eMMC/disk usage with growth rate
- Closing-in-on-full alerts at 80%, 90%, 95%, 99%
- Display overlay when approaching 100%

### 3. Regex Hook Engine
- Pattern-match stdout/stderr in real-time
- Trigger actions on compile errors, OOM, crashes
- User-definable hook patterns
- Chain hooks into automation cascades

### 4. Error Recursion → Model Feedback
- Capture all errors from batch commands
- Feed error context back to model
- Auto-retry with modified parameters (max 3)
- Tag output [AUTONOMOUSLY REPAIRED] on success

### 5. Headless Automation Cascade
- Chain commands: mine → test → deploy → verify
- Each stage feeds into the next
- Full test suite runs headless
- Results feed back into model pacing

### 6. Resource Pressure Pacing
- Auto-throttle batch queue when resources tight
- CPU > 80% → reduce parallel jobs
- Memory > 90% → pause non-critical tasks
- Disk > 95% → emergency cleanup
- Display overlay: `[CPU:45% MEM:72% DISK:88%⚠]`

## Dependencies

- Rust (for native core compilation)
- Python 3.8+ with psutil
- Termux:API (for button hooks)
- Termux:Float (for overlay display)

## License

MIT
