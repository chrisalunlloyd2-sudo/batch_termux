// Resource Pressure Display — shows CPU/MEM/DISK usage overlay
// When approaching 100%, displays persistent warning

use crate::monitor::ResourceState;

/// Display state for resource pressure overlay
pub struct DisplayState {
    pub cpu_bar: String,
    pub mem_bar: String,
    pub disk_bar: String,
    pub pressure_level: &'static str,
    pub last_output: Option<String>,
    pub last_error: Option<String>,
    pub overlay_active: bool,
}

impl DisplayState {
    pub fn new() -> Self {
        Self {
            cpu_bar: String::new(),
            mem_bar: String::new(),
            disk_bar: String::new(),
            pressure_level: "NORMAL",
            last_output: None,
            last_error: None,
            overlay_active: false,
        }
    }

    /// Update display state from resource monitor
    pub fn update(&mut self, state: &ResourceState) {
        self.cpu_bar = Self::make_bar(state.cpu_usage, 10);
        self.mem_bar = Self::make_bar(state.mem_usage, 10);
        self.disk_bar = Self::make_bar(state.disk_usage, 10);
        self.pressure_level = state.pressure_level();
        self.overlay_active = state.max_pressure() > 80.0;
    }

    /// Render the display to stderr (overlay-compatible)
    pub fn render(&self) {
        if !self.overlay_active {
            return;
        }

        let color = match self.pressure_level {
            "CRITICAL" => "\x1b[41;97m", // Red bg, white text
            "SEVERE" => "\x1b[43;30m",   // Yellow bg, black text
            "WARNING" => "\x1b[33m",     // Yellow text
            _ => "\x1b[32m",             // Green text
        };
        let reset = "\x1b[0m";

        eprintln!(
            "{color}┌─ RESOURCE PRESSURE [{pressure}] ─────────────────────┐{reset}",
            color = color,
            pressure = self.pressure_level,
            reset = reset,
        );
        eprintln!(
            "{color}│ CPU  {bar} {pct:5.1}%{reset}",
            color = color,
            bar = self.cpu_bar,
            pct = self.cpu_bar.len() as f64 * 10.0,
            reset = reset,
        );
        eprintln!(
            "{color}│ MEM  {bar} {pct:5.1}%{reset}",
            color = color,
            bar = self.mem_bar,
            pct = self.mem_bar.len() as f64 * 10.0,
            reset = reset,
        );
        eprintln!(
            "{color}│ DISK {bar} {pct:5.1}%{reset}",
            color = color,
            bar = self.disk_bar,
            pct = self.disk_bar.len() as f64 * 10.0,
            reset = reset,
        );
        eprintln!(
            "{color}└────────────────────────────────────────────────────┘{reset}",
            color = color,
            reset = reset,
        );
    }

    /// Create a simple ASCII bar (e.g., "██████░░░░" for 60%)
    fn make_bar(percent: f64, segments: usize) -> String {
        let filled = ((percent / 100.0) * segments as f64).round() as usize;
        let filled = filled.min(segments);
        let empty = segments - filled;
        format!(
            "{}{}",
            "█".repeat(filled),
            "░".repeat(empty)
        )
    }
}
