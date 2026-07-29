#!/usr/bin/env python3
"""
batch_termux — Headless Automation Cascade
Chains commands: mine → test → deploy → verify
Each stage feeds into the next. Results feed back into model pacing.

v0.2 — Wired: SIMS1337 quorum voting, matrixwince agent orchestration, oomph pacing
"""

import os
import sys
import json
import time
import subprocess
import re
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

# ── Bridges (optional — gracefully degrade if not available) ──
try:
    sys.path.insert(0, str(Path(__file__).parent.parent / "sims1337-bridge"))
    from quorum_bridge import QuorumBridge
    HAS_QUORUM = True
except ImportError:
    HAS_QUORUM = False

try:
    sys.path.insert(0, str(Path(__file__).parent.parent / "matrixwince-bridge"))
    from agent_bridge import AgentBridge
    HAS_AGENTS = True
except ImportError:
    HAS_AGENTS = False

# ── Config ──────────────────────────────────────────────────
CASCADE_DIR = Path(__file__).parent
LOG_DIR = Path("/data/data/com.termux/files/home/.batch_termux/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CASCADE] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "cascade.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("cascade")

# ── Oomph Pacing Modes ──────────────────────────────────────
OOMPH_MODES = {
    "aggressive": {
        "max_parallel": 4,
        "retry_delay": 0.5,
        "cpu_threshold": 95,
        "mem_threshold": 95,
        "disk_threshold": 98,
        "max_retries": 5,
        "description": "Full speed — push hard, retry aggressively",
    },
    "normal": {
        "max_parallel": 2,
        "retry_delay": 1.0,
        "cpu_threshold": 90,
        "mem_threshold": 90,
        "disk_threshold": 95,
        "max_retries": 3,
        "description": "Balanced — moderate pacing, standard retries",
    },
    "conservative": {
        "max_parallel": 1,
        "retry_delay": 2.0,
        "cpu_threshold": 80,
        "mem_threshold": 80,
        "disk_threshold": 90,
        "max_retries": 2,
        "description": "Careful — single file, quick to pause",
    },
    "stealth": {
        "max_parallel": 1,
        "retry_delay": 5.0,
        "cpu_threshold": 60,
        "mem_threshold": 60,
        "disk_threshold": 80,
        "max_retries": 1,
        "description": "Invisible — minimal resource use, barely tick",
    },
}


# ── Stage Definitions ────────────────────────────────────────

class CascadeStage:
    """A single stage in the automation cascade."""
    
    def __init__(self, name: str, command: str, 
                 success_pattern: str = r"success|ok|passed|done",
                 error_pattern: str = r"error|fail|crash|oom",
                 timeout: int = 60,
                 retry_count: int = 0,
                 max_retries: int = 3,
                 require_quorum: bool = False,
                 agent: Optional[str] = None):
        self.name = name
        self.command = command
        self.success_pattern = re.compile(success_pattern, re.IGNORECASE)
        self.error_pattern = re.compile(error_pattern, re.IGNORECASE)
        self.timeout = timeout
        self.retry_count = retry_count
        self.max_retries = max_retries
        self.require_quorum = require_quorum
        self.agent = agent
        self.stdout = ""
        self.stderr = ""
        self.exit_code = -1
        self.duration = 0.0
        self.passed = False
        self.fix_applied = None
        self.quorum_approved = True
        self.agent_response = None

    def run(self, oomph: str = "normal") -> bool:
        """Execute the stage command. Returns True if passed."""
        mode = OOMPH_MODES.get(oomph, OOMPH_MODES["normal"])
        
        # 1. Quorum vote (if required)
        if self.require_quorum and HAS_QUORUM:
            bridge = QuorumBridge()
            self.quorum_approved = bridge.vote_command(self.command)
            if not self.quorum_approved:
                log.warning(f"  ✗ QUORUM REJECTED: {self.command[:60]}")
                self.stderr = "[QUORUM REJECTED]"
                self.passed = False
                return False
        
        # 2. Agent pre-processing (if specified)
        if self.agent and HAS_AGENTS:
            bridge = AgentBridge()
            self.agent_response = bridge.route_command(self.command, self.agent)
            if self.agent_response:
                log.info(f"  Agent [{self.agent}]: {self.agent_response[:80]}")
        
        # 3. Execute
        log.info(f"Stage [{self.name}]: {self.command[:80]}...")
        start = time.time()
        
        try:
            result = subprocess.run(
                self.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            self.stdout = result.stdout
            self.stderr = result.stderr
            self.exit_code = result.returncode
        except subprocess.TimeoutExpired:
            self.stderr = f"[TIMEOUT] exceeded {self.timeout}s"
            self.exit_code = -1
        except Exception as e:
            self.stderr = f"[ERROR] {e}"
            self.exit_code = -1
        
        self.duration = time.time() - start
        
        # Determine pass/fail
        if self.exit_code == 0 and self.success_pattern.search(self.stdout + self.stderr):
            self.passed = True
            log.info(f"  ✓ PASSED ({self.duration:.1f}s)")
        else:
            self.passed = False
            log.warning(f"  ✗ FAILED ({self.duration:.1f}s)")
            if self.stderr:
                log.warning(f"  stderr: {self.stderr[:200]}")
        
        return self.passed
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "command": self.command,
            "passed": self.passed,
            "exit_code": self.exit_code,
            "duration": self.duration,
            "stdout_preview": self.stdout[:200] if self.stdout else "",
            "stderr_preview": self.stderr[:200] if self.stderr else "",
            "retry_count": self.retry_count,
            "fix_applied": self.fix_applied,
            "quorum_approved": self.quorum_approved,
            "agent": self.agent,
        }


class AutomationCascade:
    """Chains multiple stages together. Each stage feeds into the next."""
    
    def __init__(self, name: str = "default", oomph: str = "normal"):
        self.name = name
        self.oomph = oomph
        self.mode = OOMPH_MODES.get(oomph, OOMPH_MODES["normal"])
        self.stages: List[CascadeStage] = []
        self.results: List[dict] = []
        self.all_passed = False
        self.start_time = 0.0
        self.end_time = 0.0
    
    def set_oomph(self, mode: str):
        """Set pacing mode mid-cascade."""
        if mode in OOMPH_MODES:
            self.oomph = mode
            self.mode = OOMPH_MODES[mode]
            log.info(f"Oomph set to: {mode} — {self.mode['description']}")
    
    def add_stage(self, stage: CascadeStage):
        self.stages.append(stage)
    
    def add_stages_from_config(self, config: List[dict]):
        for c in config:
            self.add_stage(CascadeStage(
                name=c.get("name", "unnamed"),
                command=c.get("command", ""),
                success_pattern=c.get("success_pattern", r"success|ok|passed|done"),
                error_pattern=c.get("error_pattern", r"error|fail|crash|oom"),
                timeout=c.get("timeout", 60),
                require_quorum=c.get("require_quorum", False),
                agent=c.get("agent", None),
            ))
    
    def run(self) -> bool:
        """Run all stages in sequence. Stops on first failure."""
        self.start_time = time.time()
        log.info(f"═══ CASCADE [{self.name}] oomph={self.oomph} ═══")
        log.info(f"  Mode: {self.mode['description']}")
        
        for stage in self.stages:
            # Run with error recursion
            for attempt in range(self.mode["max_retries"] + 1):
                stage.retry_count = attempt
                stage.max_retries = self.mode["max_retries"]
                passed = stage.run(self.oomph)
                
                if passed:
                    break
                
                if attempt < self.mode["max_retries"]:
                    # Generate fix
                    fix = self._generate_fix(stage)
                    stage.fix_applied = fix
                    log.info(f"  ↻ Retry {attempt + 1}/{self.mode['max_retries']}: {fix}")
                    stage.command = fix
                    time.sleep(self.mode["retry_delay"])
                else:
                    log.error(f"  ✗ Stage [{stage.name}] failed after {self.mode['max_retries']} retries")
            
            self.results.append(stage.to_dict())
            
            if not stage.passed:
                self.all_passed = False
                self.end_time = time.time()
                log.warning(f"═══ CASCADE [{self.name}] FAILED at stage [{stage.name}] ═══")
                return False
        
        self.all_passed = True
        self.end_time = time.time()
        total = self.end_time - self.start_time
        log.info(f"═══ CASCADE [{self.name}] ALL PASSED ({total:.1f}s) ═══")
        return True
    
    def _generate_fix(self, stage: CascadeStage) -> str:
        """Generate a fixed command based on error analysis."""
        error = stage.stderr + stage.stdout
        
        if "Permission denied" in error:
            return f"sudo {stage.command}"
        elif "No space left" in error:
            return f"rm -rf /tmp/* 2>/dev/null; sync; {stage.command}"
        elif "command not found" in error:
            cmd = stage.command.split()[0] if stage.command.split() else ""
            return f"pkg install -y {cmd} 2>/dev/null; {stage.command}"
        elif "Connection refused" in error or "timeout" in error.lower():
            return f"sleep 2 && {stage.command}"
        elif "Segmentation fault" in error or "SIGSEGV" in error:
            return f"OMP_NUM_THREADS=1 {stage.command}"
        elif "Out of memory" in error or "Killed" in error:
            return f"MALLOC_ARENA_MAX=1 {stage.command}"
        else:
            return f"sleep 1 && {stage.command}"
    
    def save_results(self, path: Optional[Path] = None):
        """Save cascade results to JSON."""
        if path is None:
            path = LOG_DIR / f"cascade_{int(time.time())}.json"
        
        data = {
            "cascade_name": self.name,
            "oomph": self.oomph,
            "timestamp": time.time(),
            "all_passed": self.all_passed,
            "total_duration": self.end_time - self.start_time,
            "stages": self.results,
        }
        
        path.write_text(json.dumps(data, indent=2))
        log.info(f"Results saved to {path}")
        return path


# ── Default Cascade Configs ─────────────────────────────────

DEFAULT_CASCADES = {
    "code_mine": [
        {"name": "scan", "command": "find . -name '*.py' -o -name '*.rs' -o -name '*.java' | head -20", "timeout": 10},
        {"name": "lint", "command": "pylint --version 2>/dev/null && echo 'lint ok' || echo 'no pylint'", "timeout": 10},
        {"name": "test", "command": "python3 -m pytest --version 2>/dev/null && echo 'pytest ok' || echo 'no pytest'", "timeout": 10},
        {"name": "compile", "command": "rustc --version 2>/dev/null && echo 'rustc ok' || echo 'no rustc'", "timeout": 10},
    ],
    "deploy": [
        {"name": "build", "command": "echo 'build stage'", "timeout": 30},
        {"name": "test", "command": "echo 'test stage'", "timeout": 30},
        {"name": "deploy", "command": "echo 'deploy stage'", "timeout": 30, "require_quorum": True},
        {"name": "verify", "command": "echo 'verify stage'", "timeout": 30},
    ],
    "full_pipeline": [
        {"name": "mine", "command": "echo 'mining...'", "timeout": 60, "agent": "miner"},
        {"name": "code_gen", "command": "echo 'generating...'", "timeout": 60, "agent": "coder"},
        {"name": "review", "command": "echo 'reviewing...'", "timeout": 60, "agent": "critic"},
        {"name": "vote", "command": "echo 'voting...'", "timeout": 60, "require_quorum": True},
        {"name": "deploy", "command": "echo 'deploying...'", "timeout": 60, "require_quorum": True},
        {"name": "verify", "command": "echo 'verifying...'", "timeout": 60},
    ],
}


# ── CLI Entry Point ─────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="batch_termux Automation Cascade")
    parser.add_argument("cascade", nargs="?", default="code_mine",
                        choices=list(DEFAULT_CASCADES.keys()) + ["custom"],
                        help="Cascade to run")
    parser.add_argument("--command", "-c", help="Custom command for custom cascade")
    parser.add_argument("--oomph", "-o", default="normal",
                        choices=list(OOMPH_MODES.keys()),
                        help="Pacing mode")
    parser.add_argument("--save", "-s", action="store_true", help="Save results to JSON")
    parser.add_argument("--list-modes", "-l", action="store_true", help="List oomph modes")
    
    args = parser.parse_args()
    
    if args.list_modes:
        print("Oomph Pacing Modes:")
        print("=" * 50)
        for name, mode in OOMPH_MODES.items():
            print(f"  {name:15s} — {mode['description']}")
            print(f"                 max_parallel={mode['max_parallel']}, "
                  f"retry_delay={mode['retry_delay']}s, "
                  f"max_retries={mode['max_retries']}")
        sys.exit(0)
    
    if args.cascade == "custom" and args.command:
        cascade = AutomationCascade("custom", oomph=args.oomph)
        cascade.add_stage(CascadeStage("run", args.command))
    elif args.cascade in DEFAULT_CASCADES:
        cascade = AutomationCascade(args.cascade, oomph=args.oomph)
        cascade.add_stages_from_config(DEFAULT_CASCADES[args.cascade])
    else:
        print(f"Unknown cascade: {args.cascade}")
        sys.exit(1)
    
    success = cascade.run()
    
    if args.save:
        cascade.save_results()
    
    sys.exit(0 if success else 1)
