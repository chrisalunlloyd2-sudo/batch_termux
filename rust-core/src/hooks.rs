// Regex Hook Engine — pattern-match stdout/stderr in real-time
// Triggers actions on compile errors, OOM, crashes, and user-defined patterns

use std::collections::HashMap;
use regex::Regex;

/// A single hook definition
#[derive(Debug, Clone)]
pub struct Hook {
    pub name: String,
    pub pattern: String,
    pub compiled: Option<Regex>,
    pub action: HookAction,
    pub enabled: bool,
    pub hit_count: u64,
}

/// What to do when a hook pattern matches
#[derive(Debug, Clone)]
pub enum HookAction {
    /// Log the match and continue
    Log,
    /// Pause the batch queue
    Pause,
    /// Trigger error recursion (feed to model)
    ErrorRecursion,
    /// Run a shell command
    ShellCommand(String),
    /// Kill the current process
    Kill,
    /// Emergency cleanup (free memory, clear caches)
    EmergencyCleanup,
}

impl Hook {
    pub fn new(name: &str, pattern: &str, action: HookAction) -> Self {
        let compiled = Regex::new(pattern).ok();
        Self {
            name: name.to_string(),
            pattern: pattern.to_string(),
            compiled,
            action,
            enabled: true,
            hit_count: 0,
        }
    }

    pub fn matches(&self, text: &str) -> bool {
        if !self.enabled {
            return false;
        }
        if let Some(ref re) = self.compiled {
            re.is_match(text)
        } else {
            text.contains(&self.pattern)
        }
    }
}

/// Hook engine — manages all hooks and checks output
pub struct HookEngine {
    hooks: Vec<Hook>,
}

impl HookEngine {
    pub fn new() -> Self {
        let mut engine = Self { hooks: Vec::new() };
        engine.load_defaults();
        engine
    }

    /// Load default hooks for common error patterns
    fn load_defaults(&mut self) {
        // Compile errors
        self.add(Hook::new(
            "compile_error",
            r"error\[E\d{4}\]:|error:.*compile|fatal error",
            HookAction::ErrorRecursion,
        ));
        // Out of memory
        self.add(Hook::new(
            "oom_kill",
            r"Out of memory|Killed process|OOM|oom-killer",
            HookAction::EmergencyCleanup,
        ));
        // Crash / segfault
        self.add(Hook::new(
            "crash",
            r"Segmentation fault|SIGSEGV|SIGABRT|panic:|abort",
            HookAction::Pause,
        ));
        // Disk full
        self.add(Hook::new(
            "disk_full",
            r"No space left on device|Disk quota exceeded",
            HookAction::EmergencyCleanup,
        ));
        // Timeout
        self.add(Hook::new(
            "timeout",
            r"timed? ?out|Timeout|killed by signal",
            HookAction::ErrorRecursion,
        ));
        // Permission denied
        self.add(Hook::new(
            "permission",
            r"Permission denied|Operation not permitted",
            HookAction::Log,
        ));
        // Python traceback
        self.add(Hook::new(
            "python_error",
            r"Traceback \(most recent call last\)|SyntaxError|ImportError|ModuleNotFoundError",
            HookAction::ErrorRecursion,
        ));
        // Rust panic
        self.add(Hook::new(
            "rust_panic",
            r"thread '.*' panicked at",
            HookAction::ErrorRecursion,
        ));
    }

    pub fn add(&mut self, hook: Hook) {
        self.hooks.push(hook);
    }

    pub fn remove(&mut self, name: &str) {
        self.hooks.retain(|h| h.name != name);
    }

    /// Check all hooks against stdout and stderr
    /// Returns list of matching hook names
    pub fn check_all(&mut self, stdout: &str, stderr: &str) -> Vec<String> {
        let mut matches = Vec::new();
        let combined = format!("{}\n{}", stdout, stderr);

        for hook in &mut self.hooks {
            if hook.matches(&combined) {
                hook.hit_count += 1;
                matches.push(hook.name.clone());
            }
        }

        matches
    }

    /// Get all hooks with their stats
    pub fn get_stats(&self) -> Vec<(&str, u64, bool)> {
        self.hooks.iter().map(|h| (h.name.as_str(), h.hit_count, h.enabled)).collect()
    }

    pub fn len(&self) -> usize {
        self.hooks.len()
    }
}
