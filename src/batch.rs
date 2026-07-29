// Batch Command Queue — priority-ordered execution with retry support

use std::collections::VecDeque;

/// A single batch command with priority and retry tracking
#[derive(Debug, Clone)]
pub struct BatchCommand {
    pub command: String,
    pub priority: i32,          // Higher = runs first
    pub retry_count: u32,
    pub max_retries: u32,
}

impl BatchCommand {
    pub fn new(cmd: &str) -> Self {
        Self {
            command: cmd.to_string(),
            priority: 0,
            retry_count: 0,
            max_retries: 3,
        }
    }

    pub fn with_priority(cmd: &str, priority: i32) -> Self {
        Self {
            command: cmd.to_string(),
            priority,
            retry_count: 0,
            max_retries: 3,
        }
    }
}

/// Priority-sorted batch queue
pub struct BatchQueue {
    commands: Vec<BatchCommand>,
}

impl BatchQueue {
    pub fn new() -> Self {
        Self { commands: Vec::new() }
    }

    pub fn push(&mut self, cmd: BatchCommand) {
        self.commands.push(cmd);
        // Sort by priority descending
        self.commands.sort_by(|a, b| b.priority.cmp(&a.priority));
    }

    pub fn pop(&mut self) -> Option<BatchCommand> {
        if self.commands.is_empty() {
            None
        } else {
            Some(self.commands.remove(0))
        }
    }

    pub fn peek(&self) -> Option<&BatchCommand> {
        self.commands.first()
    }

    pub fn is_empty(&self) -> bool {
        self.commands.is_empty()
    }

    pub fn len(&self) -> usize {
        self.commands.len()
    }

    pub fn clear(&self) {
        // no-op in this simple version
    }

    /// Drain all commands (for shutdown)
    pub fn drain(&mut self) -> Vec<BatchCommand> {
        std::mem::take(&mut self.commands)
    }
}
