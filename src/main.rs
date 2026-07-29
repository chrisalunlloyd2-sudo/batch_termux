// batch_termux — Persistent batch terminal for Termux
// Rust native core: heartbeat pacer, batch queue, resource monitor, regex hooks, error recursion

mod pacer;
mod batch;
mod monitor;
mod hooks;
mod error_recursion;
mod display;

use std::sync::{Arc, Mutex, atomic::{AtomicBool, Ordering}};
use std::thread;
use std::time::Duration;

/// Main entry point — starts all subsystems
fn main() {
    println!("batch_termux v0.1.0 — Persistent Batch Terminal");
    println!("  subsystems: pacer | batch | monitor | hooks | error_recursion | display");

    // Shared state
    let running = Arc::new(AtomicBool::new(true));
    let r = running.clone();

    // Resource monitor (psutil-style)
    let monitor_state = Arc::new(Mutex::new(monitor::ResourceState::new()));
    let ms = monitor_state.clone();

    // Batch queue
    let batch_queue = Arc::new(Mutex::new(batch::BatchQueue::new()));
    let bq = batch_queue.clone();

    // Hook engine
    let hook_engine = Arc::new(Mutex::new(hooks::HookEngine::new()));
    let he = hook_engine.clone();

    // Error recursion engine
    let error_engine = Arc::new(Mutex::new(error_recursion::ErrorRecursionEngine::new()));
    let ee = error_engine.clone();

    // Display state
    let display_state = Arc::new(Mutex::new(display::DisplayState::new()));
    let ds = display_state.clone();

    // ── Heartbeat Pacer (50ms tick) ──
    let pacer_handle = {
        let r = r.clone();
        let ms = ms.clone();
        let bq = bq.clone();
        let he = he.clone();
        let ee = ee.clone();
        let ds = ds.clone();
        thread::spawn(move || {
            pacer::run_pacer(r, ms, bq, he, ee, ds);
        })
    };

    // ── Display Updater (every 500ms) ──
    let display_handle = {
        let r = r.clone();
        let ds = ds.clone();
        let ms = ms.clone();
        thread::spawn(move || {
            while r.load(Ordering::Relaxed) {
                thread::sleep(Duration::from_millis(500));
                let state = ms.lock().unwrap();
                let mut disp = ds.lock().unwrap();
                disp.update(&state);
                disp.render();
            }
        })
    };

    // ── Main loop — read commands from stdin ──
    let mut input = String::new();
    while running.load(Ordering::Relaxed) {
        input.clear();
        match std::io::stdin().read_line(&mut input) {
            Ok(0) => break, // EOF
            Ok(_) => {
                let cmd = input.trim();
                if cmd.is_empty() { continue; }
                if cmd == "exit" || cmd == "quit" {
                    running.store(false, Ordering::Relaxed);
                    break;
                }
                // Queue the command
                let mut queue = batch_queue.lock().unwrap();
                queue.push(batch::BatchCommand {
                    command: cmd.to_string(),
                    priority: 0,
                    retry_count: 0,
                    max_retries: 3,
                });
            }
            Err(e) => {
                eprintln!("Input error: {}", e);
                break;
            }
        }
    }

    pacer_handle.join().ok();
    display_handle.join().ok();
    println!("batch_termux shutdown complete.");
}
