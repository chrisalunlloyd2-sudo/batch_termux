// Heartbeat Pacer — 50ms tick scheduler with resource-aware pacing
// Ported from nova-terminal's heartbeat pacer concept

use std::sync::{Arc, Mutex, atomic::{AtomicBool, Ordering}};
use std::time::{Duration, Instant};
use std::thread;

use crate::monitor::ResourceState;
use crate::hooks::HookEngine;
use crate::error_recursion::ErrorRecursionEngine;
use crate::display::DisplayState;

/// Runs the heartbeat pacer loop at 50ms intervals
/// Auto-throttles based on resource pressure
pub fn run_pacer(
    running: Arc<AtomicBool>,
    monitor_state: Arc<Mutex<ResourceState>>,
    batch_queue: Arc<Mutex<Vec<BatchCommand>>>,
    hook_engine: Arc<Mutex<HookEngine>>,
    error_engine: Arc<Mutex<ErrorRecursionEngine>>,
    display_state: Arc<Mutex<DisplayState>>,
) {
    let mut tick_count: u64 = 0;

    while running.load(Ordering::Relaxed) {
        let tick_start = Instant::now();

        // 1. Update resource monitor (every 20 ticks = 1s)
        if tick_count % 20 == 0 {
            let mut state = monitor_state.lock().unwrap();
            state.poll();
        }

        // 2. Calculate pacing delay based on resource pressure
        let delay_factor = {
            let state = monitor_state.lock().unwrap();
            let max_usage = state.cpu_usage.max(state.mem_usage).max(state.disk_usage);
            if max_usage > 95.0 { 0.1 }      // Critical — barely tick
            else if max_usage > 90.0 { 0.25 } // Severe — slow down
            else if max_usage > 80.0 { 0.5 }  // Warning — half speed
            else { 1.0 }                      // Normal
        };

        // 3. Process batch queue (every 10 ticks, scaled by delay)
        let process_interval = (10.0 / delay_factor) as u64;
        if tick_count % process_interval.max(2) == 0 {
            let mut queue = batch_queue.lock().unwrap();
            if !queue.is_empty() {
                let cmd = queue.remove(0);
                drop(queue); // release lock before execution

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

        // 4. Update display pressure (every 100 ticks = 5s)
        if tick_count % 100 == 0 {
            let state = monitor_state.lock().unwrap();
            let mut disp = display_state.lock().unwrap();
            disp.update(&state);
        }

        tick_count += 1;

        // Maintain 50ms tick rate (adjusted for delay factor)
        let elapsed = tick_start.elapsed();
        let target_tick = Duration::from_millis((50.0 / delay_factor) as u64);
        if elapsed < target_tick {
            thread::sleep(target_tick - elapsed);
        }
    }
}

/// A batch command with priority and retry tracking
#[derive(Debug, Clone)]
pub struct BatchCommand {
    pub command: String,
    pub priority: i32,
    pub retry_count: u32,
    pub max_retries: u32,
    pub source: String, // "user", "hook", "cascade", "error_recursion"
}

impl BatchCommand {
    pub fn new(cmd: &str, source: &str) -> Self {
        Self {
            command: cmd.to_string(),
            priority: 0,
            retry_count: 0,
            max_retries: 3,
            source: source.to_string(),
        }
    }
}
