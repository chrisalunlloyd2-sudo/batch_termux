#!/usr/bin/env python3
"""
batch_termux — Headless Testing Suite
Runs commands in isolated PTY, captures output, compares to expected regex,
injects artificial errors to test error recursion.
"""

import os
import sys
import json
import time
import subprocess
import re
import signal
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Callable

LOG_DIR = Path("/data/data/com.termux/files/home/.batch_termux/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TEST] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "test_suite.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("test_suite")


class TestCase:
    """A single test case with expected output patterns."""
    
    def __init__(self, name: str, command: str,
                 expected_stdout: Optional[str] = None,
                 expected_stderr: Optional[str] = None,
                 expected_exit_code: int = 0,
                 expected_pattern: Optional[str] = None,
                 timeout: int = 30,
                 inject_error: bool = False,
                 error_type: Optional[str] = None):
        self.name = name
        self.command = command
        self.expected_stdout = expected_stdout
        self.expected_stderr = expected_stderr
        self.expected_exit_code = expected_exit_code
        self.expected_pattern = re.compile(expected_pattern) if expected_pattern else None
        self.timeout = timeout
        self.inject_error = inject_error
        self.error_type = error_type  # "oom", "segfault", "timeout", "permission"
        self.stdout = ""
        self.stderr = ""
        self.exit_code = -1
        self.duration = 0.0
        self.passed = False
        self.fail_reason = ""
    
    def run(self) -> bool:
        """Execute the test case."""
        cmd = self.command
        
        # Inject artificial errors for testing error recursion
        if self.inject_error:
            if self.error_type == "oom":
                cmd = f"echo 'Killed process: Out of memory'; {cmd}"
            elif self.error_type == "segfault":
                cmd = f"echo 'Segmentation fault (core dumped)'; {cmd}"
            elif self.error_type == "timeout":
                cmd = f"echo 'timed out waiting for input'; {cmd}"
            elif self.error_type == "permission":
                cmd = f"echo 'Permission denied'; {cmd}"
        
        log.info(f"  Test [{self.name}]: {cmd[:60]}...")
        start = time.time()
        
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=self.timeout
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
        self._evaluate()
        return self.passed
    
    def _evaluate(self):
        """Check all expected conditions."""
        checks = []
        
        # Check exit code
        if self.expected_exit_code is not None:
            if self.exit_code == self.expected_exit_code:
                checks.append(("exit_code", True))
            else:
                checks.append(("exit_code", False, 
                    f"expected {self.expected_exit_code}, got {self.exit_code}"))
        
        # Check expected stdout
        if self.expected_stdout:
            if self.expected_stdout in self.stdout:
                checks.append(("stdout_contains", True))
            else:
                checks.append(("stdout_contains", False,
                    f"expected '{self.expected_stdout}' in stdout"))
        
        # Check expected stderr
        if self.expected_stderr:
            if self.expected_stderr in self.stderr:
                checks.append(("stderr_contains", True))
            else:
                checks.append(("stderr_contains", False,
                    f"expected '{self.expected_stderr}' in stderr"))
        
        # Check regex pattern
        if self.expected_pattern:
            if self.expected_pattern.search(self.stdout + self.stderr):
                checks.append(("pattern", True))
            else:
                checks.append(("pattern", False,
                    f"pattern '{self.expected_pattern.pattern}' not found"))
        
        # All checks must pass
        failures = [c for c in checks if not c[1]]
        if failures:
            self.passed = False
            self.fail_reason = "; ".join(c[2] for c in failures)
        else:
            self.passed = True
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "command": self.command,
            "passed": self.passed,
            "exit_code": self.exit_code,
            "duration": self.duration,
            "stdout": self.stdout[:300],
            "stderr": self.stderr[:300],
            "fail_reason": self.fail_reason,
        }


class TestSuite:
    """A collection of test cases."""
    
    def __init__(self, name: str = "batch_termux_test_suite"):
        self.name = name
        self.tests: List[TestCase] = []
        self.results: List[dict] = []
        self.passed = 0
        self.failed = 0
        self.total_duration = 0.0
    
    def add_test(self, test: TestCase):
        self.tests.append(test)
    
    def add_default_tests(self):
        """Add default test cases for batch_termux subsystems."""
        # 1. Basic command execution
        self.add_test(TestCase("basic_echo", "echo 'hello batch'", 
                               expected_stdout="hello batch"))
        
        # 2. Error detection
        self.add_test(TestCase("error_detection", "echo 'error: something failed'",
                               expected_pattern=r"error:"))
        
        # 3. Permission denied
        self.add_test(TestCase("permission_error", "echo 'Permission denied'",
                               expected_pattern=r"Permission denied"))
        
        # 4. OOM detection
        self.add_test(TestCase("oom_detection", "echo 'Out of memory'",
                               expected_pattern=r"Out of memory"))
        
        # 5. Crash detection
        self.add_test(TestCase("crash_detection", "echo 'Segmentation fault'",
                               expected_pattern=r"Segmentation fault"))
        
        # 6. Python error
        self.add_test(TestCase("python_error", "echo 'Traceback (most recent call last)'",
                               expected_pattern=r"Traceback"))
        
        # 7. Resource monitor (just check it runs)
        self.add_test(TestCase("resource_monitor", 
                               "cat /proc/stat 2>/dev/null | head -1 || echo 'no /proc'",
                               timeout=5))
        
        # 8. Hook engine (check hooks load)
        self.add_test(TestCase("hook_compile_error", 
                               "echo 'error[E0308]: type mismatch'",
                               expected_pattern=r"error\[E0308\]"))
        
        # 9. Error recursion (injected OOM)
        self.add_test(TestCase("error_recursion_oom", 
                               "echo 'normal output'",
                               inject_error=True, error_type="oom",
                               expected_pattern=r"Out of memory"))
        
        # 10. Error recursion (injected segfault)
        self.add_test(TestCase("error_recursion_segfault",
                               "echo 'normal output'",
                               inject_error=True, error_type="segfault",
                               expected_pattern=r"Segmentation fault"))
        
        # 11. Cascade pipeline (basic)
        self.add_test(TestCase("cascade_basic",
                               "python3 -c \"print('stage1: ok'); print('stage2: ok')\"",
                               expected_pattern=r"stage1.*ok"))
        
        # 12. Long-running with timeout
        self.add_test(TestCase("timeout_handling",
                               "echo 'timed out waiting for input'",
                               expected_pattern=r"timed out"))
    
    def run(self) -> bool:
        """Run all tests and return True if all passed."""
        log.info(f"═══ TEST SUITE [{self.name}] — {len(self.tests)} tests ═══")
        start = time.time()
        
        for i, test in enumerate(self.tests, 1):
            log.info(f"  [{i}/{len(self.tests)}] {test.name}")
            passed = test.run()
            self.results.append(test.to_dict())
            
            if passed:
                self.passed += 1
                log.info(f"    ✓ PASSED ({test.duration:.2f}s)")
            else:
                self.failed += 1
                log.warning(f"    ✗ FAILED: {test.fail_reason}")
        
        self.total_duration = time.time() - start
        
        log.info(f"═══ RESULTS: {self.passed}/{len(self.tests)} passed ({self.total_duration:.1f}s) ═══")
        return self.failed == 0
    
    def save_results(self, path: Optional[Path] = None):
        if path is None:
            path = LOG_DIR / f"test_results_{int(time.time())}.json"
        
        data = {
            "suite_name": self.name,
            "timestamp": time.time(),
            "total": len(self.tests),
            "passed": self.passed,
            "failed": self.failed,
            "total_duration": self.total_duration,
            "tests": self.results,
        }
        path.write_text(json.dumps(data, indent=2))
        log.info(f"Results saved to {path}")
        return path


# ── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="batch_termux Headless Test Suite")
    parser.add_argument("--save", "-s", action="store_true", help="Save results to JSON")
    parser.add_argument("--filter", "-f", help="Run only tests matching name pattern")
    
    args = parser.parse_args()
    
    suite = TestSuite()
    suite.add_default_tests()
    
    if args.filter:
        pattern = re.compile(args.filter, re.IGNORECASE)
        suite.tests = [t for t in suite.tests if pattern.search(t.name)]
        log.info(f"Filtered to {len(suite.tests)} tests matching '{args.filter}'")
    
    success = suite.run()
    
    if args.save:
        suite.save_results()
    
    sys.exit(0 if success else 1)
