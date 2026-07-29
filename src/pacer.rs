// Heartbeat Pacer — 50ms tick scheduler
// Ported from nova-terminal's heartbeat pacer concept

use std::sync::{Arc, Mutex, atomic::{AtomicBool, Ordering}};
use std::time::{Duration, Instant};
use std::thread;

use crate::batch::BatchQueue;
use crate::monitor::ResourceState;
use crate::hooks::HookEngine;
use crate::error_recursion::ErrorRecursionEngine;
use crate::display::DisplayState;

/// Runs the heartbeat pacer loop at 50ms intervals
pub fn run_pacer(
    running: Arc<AtomicBool>,
    monitor_state: Arc<Mutex<ResourceState>>,
    batch_queue: Arc<Mutex<BatchQueue>>,
    hook_engine: Arc<Mutex<HookEngine>>,
    error_engine: Arc<Mutex<ErrorRecursionEngine>>,
    display_state: Arc<Mutex<DisplayState>>,
) {
    let mut tick_count: u64 = 0;
    let mut last_second = Instant::now();
    let mut ticks_this_second = 0u64;

    while running.load(Ordering::Relaxed) {
        let tick_start = Instant::now();

        // 1. Update resource monitor (every 20 ticks = 1s)
        if tick_count % 20 == 0 {
            let mut state = monitor_state.lock().unwrap();
            state.poll();
        }

        // 2. Process batch queue (every 10 ticks = 500ms)
        if tick_count % 10 == 0 {
            let mut queue = batch_queue.lock().unwrap();
            if !queue.is_empty() {
                if let Some(cmd) = queue.pop() {
                    // Execute via system shell
                    let output = std::process::Command::new("sh")
                        .arg("-c")
                        .arg(&cmd.command)
                        .output();

                    match output {
                        Ok(out) => {
                            let stdout = String::from_utf8_lossy(&out.stdout).to_string();
                            let stderr = String::from_utf8_lossy(&out.stderr).to_string();

                            // Check hooks on output
                            let mut hooks = hook_engine.lock().unwrap();
                            let hook_matches = hooks.check_all(&stdout, &stderr);

                            // Check for errors → recursion
                            if !out.status.success() || !hook_matches.is_empty() {
                                let mut err_engine = error_engine.lock().unwrap();
                                let retry_cmd = err_engine.process_error(
                                    &cmd.command,
                                    &stdout,
                                    &stderr,
                                    &hook_matches,
                                );
                                if let Some(retry) = retry_cmd {
                                    // Re-queue with modified params
                                    let mut queue2 = batch_queue.lock().unwrap();
                                    queue2.push(retry);
                                }
                            }

                            // Update display
                            let mut disp = display_state.lock().unwrap();
                            disp.last_output = Some(format!("$ {}\n{}", cmd.command, stdout));
                            if !stderr.is_empty() {
                                disp.last_error = Some(stderr);
                            }
                        }
                        Err(e) => {
                            let mut disp = display_state.lock().unwrap();
                            disp.last_error = Some(format!("Execution error: {}", e));
                        }
                    }
                }
            }
        }

        // 3. Update display pressure (every 100 ticks = 5s)
        if tick_count % 100 == 0 {
            let state = monitor_state.lock().unwrap();
            let mut disp = display_state.lock().unwrap();
            disp.update(&state);
        }

        // Tick accounting
        tick_count += 1;
        ticks_this_second += 1;

        // Reset per-second counter
        if last_second.elapsed() >= Duration::from_secs(1) {
            last_second = Instant::now();
            ticks_this_second = 0;
        }

        // Maintain 50ms tick rate
        let elapsed = tick_start.elapsed();
        if elapsed < Duration::from_millis(50) {
            thread::sleep(Duration::from_millis(50) - elapsed);
        }
    }
}
