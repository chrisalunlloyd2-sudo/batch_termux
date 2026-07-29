// Heartbeat Pacer — 50ms tick scheduler with resource-aware pacing
// v0.2 — Oomph pacing modes: aggressive, normal, conservative, stealth

use std::sync::{Arc, Mutex, atomic::{AtomicBool, AtomicU8, Ordering}};
use std::time::{Duration, Instant};
use std::thread;

use crate::monitor::ResourceState;
use crate::hooks::HookEngine;
use crate::error_recursion::ErrorRecursionEngine;
use crate::display::DisplayState;

/// Oomph pacing modes
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum OomphMode {
    Aggressive = 0,   // Full speed, push hard
    Normal = 1,        // Balanced
    Conservative = 2,  // Careful, quick to pause
    Stealth = 3,       // Minimal resource use
}

impl OomphMode {
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "aggressive" => OomphMode::Aggressive,
            "conservative" => OomphMode::Conservative,
            "stealth" => OomphMode::Stealth,
            _ => OomphMode::Normal,
        }
    }

    pub fn cpu_threshold(&self) -> f64 {
        match self {
            OomphMode::Aggressive => 95.0,
            OomphMode::Normal => 90.0,
            OomphMode::Conservative => 80.0,
            OomphMode::Stealth => 60.0,
        }
    }

    pub fn mem_threshold(&self) -> f64 {
        match self {
            OomphMode::Aggressive => 95.0,
            OomphMode::Normal => 90.0,
            OomphMode::Conservative => 80.0,
            OomphMode::Stealth => 60.0,
        }
    }

    pub fn disk_threshold(&self) -> f64 {
        match self {
            OomphMode::Aggressive => 98.0,
            OomphMode::Normal => 95.0,
            OomphMode::Conservative => 90.0,
            OomphMode::Stealth => 80.0,
        }
    }

    pub fn max_parallel(&self) -> u32 {
        match self {
            OomphMode::Aggressive => 4,
            OomphMode::Normal => 2,
            OomphMode::Conservative => 1,
            OomphMode::Stealth => 1,
        }
    }

    pub fn retry_delay_ms(&self) -> u64 {
        match self {
            OomphMode::Aggressive => 500,
            OomphMode::Normal => 1000,
            OomphMode::Conservative => 2000,
            OomphMode::Stealth => 5000,
        }
    }

    pub fn max_retries(&self) -> u32 {
        match self {
            OomphMode::Aggressive => 5,
            OomphMode::Normal => 3,
            OomphMode::Conservative => 2,
            OomphMode::Stealth => 1,
        }
    }
}

/// Runs the heartbeat pacer loop at 50ms intervals
/// Auto-throttles based on resource pressure and oomph mode
pub fn run_pacer(
    running: Arc<AtomicBool>,
    oomph: Arc<AtomicU8>,
    monitor_state: Arc<Mutex<ResourceState>>,
    batch_queue: Arc<Mutex<Vec<BatchCommand>>>,
    hook_engine: Arc<Mutex<HookEngine>>,
    error_engine: Arc<Mutex<ErrorRecursionEngine>>,
    display_state: Arc<Mutex<DisplayState>>,
) {
    let mut tick_count: u64 = 0;

    while running.load(Ordering::Relaxed) {
        let tick_start = Instant::now();
        let mode = OomphMode::from_u8(oomph.load(Ordering::Relaxed));

        // 1. Update resource monitor (every 20 ticks = 1s)
        if tick_count % 20 == 0 {
            let mut state = monitor_state.lock().unwrap();
            state.poll();
        }

        // 2. Calculate pacing delay based on resource pressure + oomph mode
        let delay_factor = {
            let state = monitor_state.lock().unwrap();
            let cpu_t = mode.cpu_threshold();
            let mem_t = mode.mem_threshold();
            let disk_t = mode.disk_threshold();
            
            let cpu_pressure = if state.cpu_usage > cpu_t { (state.cpu_usage - cpu_t) / (100.0 - cpu_t) } else { 0.0 };
            let mem_pressure = if state.mem_usage > mem_t { (state.mem_usage - mem_t) / (100.0 - mem_t) } else { 0.0 };
            let disk_pressure = if state.disk_usage > disk_t { (state.disk_usage - disk_t) / (100.0 - disk_t) } else { 0.0 };
            
            let max_pressure = cpu_pressure.max(mem_pressure).max(disk_pressure);
            (1.0 - max_pressure).max(0.1) // 0.1 to 1.0
        };

        // 3. Process batch queue (paced by oomph mode)
        let process_interval = (10.0 / delay_factor) as u64;
        if tick_count % process_interval.max(2) == 0 {
            let mut queue = batch_queue.lock().unwrap();
            if !queue.is_empty() {
                let cmd = queue.remove(0);
                drop(queue);

                let output = std::process::Command::new("sh")
                    .arg("-c")
                    .arg(&cmd.command)
                    .output();

                match output {
                    Ok(out) => {
                        let stdout = String::from_utf8_lossy(&out.stdout).to_string();
                        let stderr = String::from_utf8_lossy(&out.stderr).to_string();

                        let mut hooks = hook_engine.lock().unwrap();
                        let hook_matches = hooks.check_all(&stdout, &stderr);

                        if !out.status.success() || !hook_matches.is_empty() {
                            let mut err_engine = error_engine.lock().unwrap();
                            let retry_cmd = err_engine.process_error(
                                &cmd.command,
                                &stdout,
                                &stderr,
                                &hook_matches,
                                mode.max_retries(),
                            );
                            if let Some(retry) = retry_cmd {
                                let mut queue2 = batch_queue.lock().unwrap();
                                queue2.push(retry);
                            }
                        }

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

        // Maintain tick rate (adjusted for oomph mode + delay factor)
        let elapsed = tick_start.elapsed();
        let base_tick_ms = match mode {
            OomphMode::Aggressive => 25,
            OomphMode::Normal => 50,
            OomphMode::Conservative => 100,
            OomphMode::Stealth => 250,
        };
        let target_tick = Duration::from_millis((base_tick_ms as f64 / delay_factor) as u64);
        if elapsed < target_tick {
            thread::sleep(target_tick - elapsed);
        }
    }
}

impl OomphMode {
    pub fn from_u8(v: u8) -> Self {
        match v {
            0 => OomphMode::Aggressive,
            1 => OomphMode::Normal,
            2 => OomphMode::Conservative,
            3 => OomphMode::Stealth,
            _ => OomphMode::Normal,
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
    pub source: String,
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
