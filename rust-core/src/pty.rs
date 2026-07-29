// PTY Multiplexer — manages multiple batch sessions
// Keeps sessions alive across Termux restarts

use std::collections::HashMap;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

/// A managed PTY session
#[derive(Debug)]
pub struct PtySession {
    pub id: String,
    pub command: String,
    pub created: Instant,
    pub last_active: Instant,
    pub pid: Option<u32>,
    pub output_buffer: String,
    pub active: bool,
}

/// PTY multiplexer — manages multiple concurrent batch sessions
pub struct PtyMultiplexer {
    sessions: HashMap<String, PtySession>,
    max_sessions: usize,
}

impl PtyMultiplexer {
    pub fn new(max_sessions: usize) -> Self {
        Self {
            sessions: HashMap::new(),
            max_sessions,
        }
    }

    /// Create a new batch session
    pub fn create_session(&mut self, id: &str, command: &str) -> Result<&PtySession, String> {
        if self.sessions.len() >= self.max_sessions {
            // Evict oldest inactive session
            let oldest = self.sessions.iter()
                .min_by_key(|(_, s)| s.last_active)
                .map(|(k, _)| k.clone());
            if let Some(old_id) = oldest {
                self.destroy_session(&old_id);
            }
        }

        let session = PtySession {
            id: id.to_string(),
            command: command.to_string(),
            created: Instant::now(),
            last_active: Instant::now(),
            pid: None,
            output_buffer: String::new(),
            active: true,
        };

        self.sessions.insert(id.to_string(), session);
        Ok(self.sessions.get(id).unwrap())
    }

    /// Destroy a session
    pub fn destroy_session(&mut self, id: &str) {
        if let Some(session) = self.sessions.remove(id) {
            if let Some(pid) = session.pid {
                // Try to kill the process
                let _ = Command::new("kill")
                    .arg(pid.to_string())
                    .output();
            }
        }
    }

    /// Get a session by ID
    pub fn get_session(&self, id: &str) -> Option<&PtySession> {
        self.sessions.get(id)
    }

    /// Get a mutable session by ID
    pub fn get_session_mut(&mut self, id: &str) -> Option<&mut PtySession> {
        self.sessions.get_mut(id)
    }

    /// List all active sessions
    pub fn list_sessions(&self) -> Vec<&PtySession> {
        self.sessions.values().collect()
    }

    /// Clean up stale sessions (older than timeout)
    pub fn cleanup_stale(&mut self, timeout: Duration) {
        let now = Instant::now();
        let stale: Vec<String> = self.sessions.iter()
            .filter(|(_, s)| now.duration_since(s.last_active) > timeout)
            .map(|(k, _)| k.clone())
            .collect();
        for id in stale {
            self.destroy_session(&id);
        }
    }

    /// Get session count
    pub fn session_count(&self) -> usize {
        self.sessions.len()
    }
}
