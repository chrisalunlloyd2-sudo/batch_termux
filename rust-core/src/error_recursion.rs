// Error Recursion Engine — captures errors, feeds back to model, retries with modified params

use std::collections::VecDeque;
use std::time::Instant;

use crate::pacer::BatchCommand;

/// Error recursion record
#[derive(Debug, Clone)]
pub struct ErrorRecord {
    pub original_command: String,
    pub error_text: String,
    pub hook_matches: Vec<String>,
    pub retry_count: u32,
    pub last_retry: Option<Instant>,
    pub resolved: bool,
    pub fix_applied: Option<String>,
}

/// Error recursion engine
pub struct ErrorRecursionEngine {
    pub max_retries: u32,
    pub error_history: VecDeque<ErrorRecord>,
    pub max_history: usize,
}

impl ErrorRecursionEngine {
    pub fn new() -> Self {
        Self {
            max_retries: 3,
            error_history: VecDeque::new(),
            max_history: 100,
        }
    }

    /// Process an error — returns a modified command to retry, or None if max retries exceeded
    pub fn process_error(
        &mut self,
        command: &str,
        stdout: &str,
        stderr: &str,
        hook_matches: &[String],
    ) -> Option<BatchCommand> {
        let error_text = if !stderr.is_empty() { stderr } else { stdout };

        // Check if we already have a record for this command
        let existing = self.error_history.iter_mut()
            .find(|r| r.original_command == command && !r.resolved);

        if let Some(record) = existing {
            record.retry_count += 1;
            record.last_retry = Some(Instant::now());
            record.error_text = error_text.to_string();
            record.hook_matches = hook_matches.to_vec();

            if record.retry_count >= self.max_retries {
                record.resolved = false; // permanently failed
                return None;
            }

            // Generate a modified command based on the error
            let modified = self.generate_fix(command, error_text, hook_matches);
            record.fix_applied = Some(modified.clone());
            Some(BatchCommand::new(&modified, "error_recursion"))
        } else {
            // New error
            let record = ErrorRecord {
                original_command: command.to_string(),
                error_text: error_text.to_string(),
                hook_matches: hook_matches.to_vec(),
                retry_count: 1,
                last_retry: Some(Instant::now()),
                resolved: false,
                fix_applied: None,
            };
            self.error_history.push_back(record);
            if self.error_history.len() > self.max_history {
                self.error_history.pop_front();
            }

            // Generate a modified command
            let modified = self.generate_fix(command, error_text, hook_matches);
            Some(BatchCommand::new(&modified, "error_recursion"))
        }
    }

    /// Generate a modified command based on error analysis
    fn generate_fix(&self, command: &str, error: &str, hooks: &[String]) -> String {
        // Simple heuristic fixes based on error type
        if error.contains("Permission denied") || error.contains("Operation not permitted") {
            format!("sudo {}", command)
        } else if error.contains("No space left on device") {
            format!("rm -rf /tmp/* 2>/dev/null; sync; {}", command)
        } else if error.contains("command not found") {
            // Try with pkg install first
            let cmd_name = command.split_whitespace().next().unwrap_or("");
            format!("pkg install -y {} 2>/dev/null; {}", cmd_name, command)
        } else if error.contains("Connection refused") || error.contains("Connection timed out") {
            format!("sleep 2 && {}", command)
        } else if error.contains("Segmentation fault") || error.contains("SIGSEGV") {
            // Reduce thread count / memory usage
            format!("OMP_NUM_THREADS=1 MALLOC_ARENA_MAX=1 {}", command)
        } else if error.contains("Out of memory") || error.contains("Killed process") {
            format!("MALLOC_ARENA_MAX=1 {} 2>&1", command)
        } else if error.contains("Traceback") || error.contains("SyntaxError") {
            // Python errors — try with python3 explicitly
            format!("python3 -c \"{}\"", command.replace('"', "\\\""))
        } else {
            // Generic retry with a small delay
            format!("sleep 1 && {}", command)
        }
    }

    /// Get error history summary
    pub fn get_summary(&self) -> Vec<(&str, u32, bool)> {
        self.error_history.iter()
            .map(|r| (r.original_command.as_str(), r.retry_count, r.resolved))
            .collect()
    }

    /// Get unresolved error count
    pub fn unresolved_count(&self) -> usize {
        self.error_history.iter().filter(|r| !r.resolved).count()
    }
}
