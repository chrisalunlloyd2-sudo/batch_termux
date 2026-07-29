// Resource Monitor — psutil-style CPU, memory, disk monitoring for Android/Termux
// Reads /proc/stat, /proc/meminfo, /proc/diskstats

use std::fs;
use std::time::Instant;

/// Resource usage snapshot
#[derive(Debug, Clone, Default)]
pub struct ResourceState {
    pub cpu_usage: f64,       // 0.0 - 100.0
    pub mem_usage: f64,       // 0.0 - 100.0
    pub mem_available_mb: f64,
    pub mem_total_mb: f64,
    pub disk_usage: f64,      // 0.0 - 100.0
    pub disk_free_mb: f64,
    pub disk_total_mb: f64,
    pub swap_usage: f64,      // 0.0 - 100.0
    pub load_avg_1m: f64,
    pub load_avg_5m: f64,
    pub load_avg_15m: f64,
    pub uptime_seconds: u64,
    pub last_poll: Instant,
}

impl ResourceState {
    pub fn new() -> Self {
        Self {
            last_poll: Instant::now(),
            ..Default::default()
        }
    }

    /// Poll all resource metrics
    pub fn poll(&mut self) {
        self.poll_cpu();
        self.poll_memory();
        self.poll_disk();
        self.poll_load_avg();
        self.poll_uptime();
        self.last_poll = Instant::now();
    }

    fn poll_cpu(&mut self) {
        // Read /proc/stat for CPU usage
        if let Ok(content) = fs::read_to_string("/proc/stat") {
            for line in content.lines() {
                if line.starts_with("cpu ") {
                    let parts: Vec<&str> = line.split_whitespace().collect();
                    if parts.len() >= 5 {
                        let user: u64 = parts[1].parse().unwrap_or(0);
                        let nice: u64 = parts[2].parse().unwrap_or(0);
                        let system: u64 = parts[3].parse().unwrap_or(0);
                        let idle: u64 = parts[4].parse().unwrap_or(0);
                        let total = user + nice + system + idle;
                        if total > 0 {
                            self.cpu_usage = ((user + nice + system) as f64 / total as f64) * 100.0;
                        }
                    }
                    break;
                }
            }
        }
    }

    fn poll_memory(&mut self) {
        // Read /proc/meminfo for memory usage
        if let Ok(content) = fs::read_to_string("/proc/meminfo") {
            let mut mem_total_kb = 0u64;
            let mut mem_avail_kb = 0u64;
            let mut swap_total_kb = 0u64;
            let mut swap_free_kb = 0u64;

            for line in content.lines() {
                let parts: Vec<&str> = line.split_whitespace().collect();
                if parts.len() >= 2 {
                    let val = parts[1].parse::<u64>().unwrap_or(0);
                    if line.starts_with("MemTotal:") { mem_total_kb = val; }
                    else if line.starts_with("MemAvailable:") { mem_avail_kb = val; }
                    else if line.starts_with("SwapTotal:") { swap_total_kb = val; }
                    else if line.starts_with("SwapFree:") { swap_free_kb = val; }
                }
            }

            if mem_total_kb > 0 {
                self.mem_total_mb = mem_total_kb as f64 / 1024.0;
                self.mem_available_mb = mem_avail_kb as f64 / 1024.0;
                self.mem_usage = ((mem_total_kb - mem_avail_kb) as f64 / mem_total_kb as f64) * 100.0;
            }

            if swap_total_kb > 0 {
                self.swap_usage = ((swap_total_kb - swap_free_kb) as f64 / swap_total_kb as f64) * 100.0;
            }
        }
    }

    fn poll_disk(&mut self) {
        // Read /proc/diskstats or use statvfs on root
        #[cfg(target_os = "android")]
        {
            if let Ok(stat) = fs::metadata("/data") {
                // Use statvfs via libc
                unsafe {
                    let mut buf: libc::statvfs = std::mem::zeroed();
                    if libc::statvfs(b"/data\0".as_ptr() as *const _, &mut buf) == 0 {
                        let total = buf.f_blocks as u64 * buf.f_bsize as u64;
                        let free = buf.f_bfree as u64 * buf.f_bsize as u64;
                        if total > 0 {
                            self.disk_total_mb = total as f64 / 1048576.0;
                            self.disk_free_mb = free as f64 / 1048576.0;
                            self.disk_usage = ((total - free) as f64 / total as f64) * 100.0;
                        }
                    }
                }
            }
        }

        #[cfg(not(target_os = "android"))]
        {
            // Fallback: use df output
            if let Ok(out) = std::process::Command::new("df")
                .arg("-B1")
                .arg("/")
                .output()
            {
                let stdout = String::from_utf8_lossy(&out.stdout);
                for line in stdout.lines().skip(1) {
                    let parts: Vec<&str> = line.split_whitespace().collect();
                    if parts.len() >= 4 {
                        let total = parts[1].parse::<u64>().unwrap_or(0);
                        let used = parts[2].parse::<u64>().unwrap_or(0);
                        if total > 0 {
                            self.disk_total_mb = total as f64 / 1048576.0;
                            self.disk_free_mb = (total - used) as f64 / 1048576.0;
                            self.disk_usage = (used as f64 / total as f64) * 100.0;
                        }
                    }
                    break;
                }
            }
        }
    }

    fn poll_load_avg(&mut self) {
        if let Ok(content) = fs::read_to_string("/proc/loadavg") {
            let parts: Vec<&str> = content.split_whitespace().collect();
            if parts.len() >= 3 {
                self.load_avg_1m = parts[0].parse().unwrap_or(0.0);
                self.load_avg_5m = parts[1].parse().unwrap_or(0.0);
                self.load_avg_15m = parts[2].parse().unwrap_or(0.0);
            }
        }
    }

    fn poll_uptime(&mut self) {
        if let Ok(content) = fs::read_to_string("/proc/uptime") {
            let parts: Vec<&str> = content.split_whitespace().collect();
            if let Some(secs) = parts.first().and_then(|s| s.parse::<f64>().ok()) {
                self.uptime_seconds = secs as u64;
            }
        }
    }

    /// Get the maximum resource pressure (0.0 - 100.0)
    pub fn max_pressure(&self) -> f64 {
        self.cpu_usage.max(self.mem_usage).max(self.disk_usage)
    }

    /// Get a human-readable pressure level
    pub fn pressure_level(&self) -> &'static str {
        let p = self.max_pressure();
        if p > 95.0 { "CRITICAL" }
        else if p > 90.0 { "SEVERE" }
        else if p > 80.0 { "WARNING" }
        else if p > 60.0 { "ELEVATED" }
        else { "NORMAL" }
    }
}
