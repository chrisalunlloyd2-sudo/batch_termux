// batch_termux — Rust native core
// v0.2 — Oomph pacing modes, quorum voting bridge, agent orchestration bridge

pub mod pacer;
pub mod monitor;
pub mod hooks;
pub mod error_recursion;
pub mod display;
pub mod pty;

use std::sync::{Arc, Mutex, atomic::{AtomicBool, AtomicU8, Ordering}};
use std::thread;
use std::time::Duration;

use pacer::{OomphMode, BatchCommand};

/// Initialize all subsystems. Returns a handle that can be used to stop.
pub struct BatchTermux {
    running: Arc<AtomicBool>,
    oomph: Arc<AtomicU8>,
}

impl BatchTermux {
    pub fn start() -> Self {
        let running = Arc::new(AtomicBool::new(true));
        let oomph = Arc::new(AtomicU8::new(OomphMode::Normal as u8));
        let r = running.clone();
        let o = oomph.clone();

        let monitor_state = Arc::new(Mutex::new(monitor::ResourceState::new()));
        let batch_queue = Arc::new(Mutex::new(Vec::new()));
        let hook_engine = Arc::new(Mutex::new(hooks::HookEngine::new()));
        let error_engine = Arc::new(Mutex::new(error_recursion::ErrorRecursionEngine::new()));
        let display_state = Arc::new(Mutex::new(display::DisplayState::new()));

        // Heartbeat pacer thread
        let r1 = r.clone();
        let o1 = o.clone();
        let ms = monitor_state.clone();
        let bq = batch_queue.clone();
        let he = hook_engine.clone();
        let ee = error_engine.clone();
        let ds = display_state.clone();
        thread::spawn(move || {
            pacer::run_pacer(r1, o1, ms, bq, he, ee, ds);
        });

        // Display updater (500ms)
        let r2 = r.clone();
        let ms2 = monitor_state.clone();
        let ds2 = display_state.clone();
        thread::spawn(move || {
            while r2.load(Ordering::Relaxed) {
                thread::sleep(Duration::from_millis(500));
                let state = ms2.lock().unwrap();
                let mut disp = ds2.lock().unwrap();
                disp.update(&state);
                disp.render();
            }
        });

        Self { running, oomph }
    }

    pub fn stop(&self) {
        self.running.store(false, Ordering::Relaxed);
    }

    pub fn set_oomph(&self, mode: OomphMode) {
        self.oomph.store(mode as u8, Ordering::Relaxed);
    }
}

/// FFI entry point for Android/Java bridge
#[no_mangle]
pub extern "C" fn batch_termux_start() -> *mut BatchTermux {
    Box::into_raw(Box::new(BatchTermux::start()))
}

#[no_mangle]
pub extern "C" fn batch_termux_stop(handle: *mut BatchTermux) {
    if !handle.is_null() {
        unsafe {
            (*handle).stop();
            let _ = Box::from_raw(handle);
        }
    }
}

#[no_mangle]
pub extern "C" fn batch_termux_set_oomph(handle: *mut BatchTermux, mode: u8) {
    if !handle.is_null() {
        unsafe {
            (*handle).set_oomph(OomphMode::from_u8(mode));
        }
    }
}
