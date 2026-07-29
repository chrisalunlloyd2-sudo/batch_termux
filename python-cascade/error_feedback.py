#!/usr/bin/env python3
"""
batch_termux — Error Recursion → Model Feedback Loop
Captures errors from batch commands, feeds stack trace to model,
retries with modified parameters, logs all attempts.
"""

import os
import sys
import json
import time
import subprocess
import re
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field, asdict

LOG_DIR = Path("/data/data/com.termux/files/home/.batch_termux/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [FEEDBACK] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "error_feedback.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("error_feedback")


@dataclass
class ErrorFeedbackRecord:
    """Record of an error and its resolution attempt."""
    original_command: str
    error_text: str
    hook_matches: List[str]
    retry_count: int = 0
    max_retries: int = 3
    resolved: bool = False
    fix_applied: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    duration: float = 0.0
    model_suggestion: Optional[str] = None


class ErrorFeedbackEngine:
    """Captures errors, feeds to model, retries with fixes."""
    
    def __init__(self, max_retries: int = 3, use_model: bool = True):
        self.max_retries = max_retries
        self.use_model = use_model
        self.history: List[ErrorFeedbackRecord] = []
        self.max_history = 100
        self._fix_patterns = self._load_fix_patterns()
    
    def _load_fix_patterns(self) -> Dict[str, str]:
        """Load heuristic fix patterns for common errors."""
        return {
            r"Permission denied|Operation not permitted": "sudo {}",
            r"No space left on device|Disk quota exceeded": "rm -rf /tmp/* 2>/dev/null; sync; {}",
            r"command not found": "pkg install -y {cmd} 2>/dev/null; {}",
            r"Connection refused|Connection timed out": "sleep 2 && {}",
            r"Segmentation fault|SIGSEGV|SIGABRT": "OMP_NUM_THREADS=1 MALLOC_ARENA_MAX=1 {}",
            r"Out of memory|Killed process|oom-killer": "MALLOC_ARENA_MAX=1 {}",
            r"Traceback|SyntaxError|ImportError": "python3 -c \"{}\"",
            r"timed? ?out|Timeout": "timeout 30 {}",
        }
    
    def process(self, command: str, stdout: str, stderr: str,
                hook_matches: List[str]) -> Optional[str]:
        """
        Process an error. Returns a fixed command to retry, or None if max retries exceeded.
        """
        error_text = stderr if stderr else stdout
        
        # Check if we already have a record
        existing = [r for r in self.history 
                    if r.original_command == command and not r.resolved]
        
        if existing:
            record = existing[0]
            record.retry_count += 1
            record.error_text = error_text
            record.hook_matches = hook_matches
            
            if record.retry_count >= self.max_retries:
                record.resolved = False
                log.warning(f"Max retries ({self.max_retries}) exceeded for: {command[:60]}")
                return None
            
            # Generate fix
            fix = self._generate_fix(command, error_text, hook_matches)
            record.fix_applied = fix
            log.info(f"Retry {record.retry_count}/{self.max_retries}: {fix[:80]}")
            return fix
        else:
            # New error
            record = ErrorFeedbackRecord(
                original_command=command,
                error_text=error_text,
                hook_matches=hook_matches,
            )
            self.history.append(record)
            if len(self.history) > self.max_history:
                self.history.pop(0)
            
            fix = self._generate_fix(command, error_text, hook_matches)
            record.fix_applied = fix
            log.info(f"New error, first fix: {fix[:80]}")
            return fix
    
    def _generate_fix(self, command: str, error: str, hooks: List[str]) -> str:
        """Generate a fix command based on error analysis."""
        # Try heuristic patterns first
        for pattern, fix_template in self._fix_patterns.items():
            if re.search(pattern, error, re.IGNORECASE):
                cmd_name = command.split()[0] if command.split() else ""
                return fix_template.format(command, cmd=cmd_name)
        
        # Try model suggestion
        if self.use_model:
            try:
                from model_pacer import ModelPacer
                pacer = ModelPacer()
                suggestion = pacer.suggest_fix(error, command)
                if suggestion:
                    return suggestion
            except ImportError:
                pass
        
        # Generic fallback
        return f"sleep 1 && {command}"
    
    def get_summary(self) -> dict:
        """Get error feedback summary."""
        total = len(self.history)
        resolved = sum(1 for r in self.history if r.resolved)
        unresolved = total - resolved
        return {
            "total_errors": total,
            "resolved": resolved,
            "unresolved": unresolved,
            "recent": [asdict(r) for r in self.history[-5:]],
        }
    
    def save_history(self, path: Optional[Path] = None):
        """Save error history to JSON."""
        if path is None:
            path = LOG_DIR / f"error_history_{int(time.time())}.json"
        data = [asdict(r) for r in self.history]
        path.write_text(json.dumps(data, indent=2))
        log.info(f"History saved to {path}")


# ── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="batch_termux Error Feedback Engine")
    parser.add_argument("action", choices=["process", "summary", "save"],
                        help="Action to perform")
    parser.add_argument("--command", "-c", help="Original command that failed")
    parser.add_argument("--error", "-e", help="Error text")
    parser.add_argument("--stdout", help="Stdout from command")
    parser.add_argument("--stderr", help="Stderr from command")
    
    args = parser.parse_args()
    engine = ErrorFeedbackEngine()
    
    if args.action == "process":
        if not args.command or not (args.error or args.stderr):
            print("Need --command and --error or --stderr")
            sys.exit(1)
        fix = engine.process(
            args.command,
            args.stdout or "",
            args.stderr or args.error or "",
            [],
        )
        if fix:
            print(fix)
        else:
            print("NO_FIX")
            sys.exit(1)
    elif args.action == "summary":
        print(json.dumps(engine.get_summary(), indent=2))
    elif args.action == "save":
        engine.save_history()
