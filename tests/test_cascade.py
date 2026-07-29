#!/usr/bin/env python3
"""Tests for batch_termux automation cascade."""

import sys
import os
import json
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python-cascade'))

from cascade import AutomationCascade, CascadeStage
from error_feedback import ErrorFeedbackEngine


class TestCascadeStage(unittest.TestCase):
    
    def test_basic_command(self):
        stage = CascadeStage("echo_test", "echo 'hello batch'")
        result = stage.run()
        self.assertTrue(result)
        self.assertIn("hello batch", stage.stdout)
    
    def test_failing_command(self):
        stage = CascadeStage("fail_test", "exit 1")
        result = stage.run()
        self.assertFalse(result)
        self.assertNotEqual(stage.exit_code, 0)
    
    def test_success_pattern(self):
        stage = CascadeStage("pattern_test", "echo 'SUCCESS: all tests passed'")
        result = stage.run()
        self.assertTrue(result)
    
    def test_error_pattern(self):
        stage = CascadeStage("error_test", "echo 'ERROR: something broke'",
                             success_pattern=r"recovered")
        result = stage.run()
        self.assertFalse(result)
    
    def test_timeout(self):
        stage = CascadeStage("timeout_test", "sleep 10", timeout=1)
        result = stage.run()
        self.assertFalse(result)
        self.assertIn("TIMEOUT", stage.stderr)


class TestAutomationCascade(unittest.TestCase):
    
    def test_simple_cascade(self):
        cascade = AutomationCascade("test_simple")
        cascade.add_stage(CascadeStage("s1", "echo 'stage1 ok'"))
        cascade.add_stage(CascadeStage("s2", "echo 'stage2 ok'"))
        result = cascade.run()
        self.assertTrue(result)
        self.assertTrue(cascade.all_passed)
    
    def test_cascade_fails_at_stage2(self):
        cascade = AutomationCascade("test_fail")
        cascade.add_stage(CascadeStage("s1", "echo 'stage1 ok'"))
        cascade.add_stage(CascadeStage("s2", "exit 1"))
        cascade.add_stage(CascadeStage("s3", "echo 'should not run'"))
        result = cascade.run()
        self.assertFalse(result)
        self.assertEqual(len(cascade.results), 2)  # Only s1 and s2 ran
    
    def test_cascade_from_config(self):
        config = [
            {"name": "a", "command": "echo 'a ok'"},
            {"name": "b", "command": "echo 'b ok'"},
        ]
        cascade = AutomationCascade("test_config")
        cascade.add_stages_from_config(config)
        result = cascade.run()
        self.assertTrue(result)
    
    def test_save_results(self):
        cascade = AutomationCascade("test_save")
        cascade.add_stage(CascadeStage("s1", "echo 'ok'"))
        cascade.run()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            path = cascade.save_results(f.name)
        data = json.loads(open(path).read())
        self.assertEqual(data["cascade_name"], "test_save")
        self.assertTrue(data["all_passed"])
        os.unlink(path)


class TestErrorFeedback(unittest.TestCase):
    
    def test_new_error(self):
        engine = ErrorFeedbackEngine(max_retries=3, use_model=False)
        fix = engine.process("cargo build", "", "error[E0308]: type mismatch", [])
        self.assertIsNotNone(fix)
        self.assertEqual(len(engine.history), 1)
    
    def test_max_retries(self):
        engine = ErrorFeedbackEngine(max_retries=2, use_model=False)
        # First attempt
        fix1 = engine.process("bad_cmd", "", "error: failed", [])
        self.assertIsNotNone(fix1)
        # Second attempt
        fix2 = engine.process("bad_cmd", "", "error: failed again", [])
        self.assertIsNotNone(fix2)
        # Third attempt — should return None
        fix3 = engine.process("bad_cmd", "", "error: failed thrice", [])
        self.assertIsNone(fix3)
    
    def test_permission_fix(self):
        engine = ErrorFeedbackEngine(use_model=False)
        fix = engine.process("cat /etc/shadow", "", "Permission denied", [])
        self.assertIn("sudo", fix)
    
    def test_oom_fix(self):
        engine = ErrorFeedbackEngine(use_model=False)
        fix = engine.process("big_process", "", "Killed process: Out of memory", [])
        self.assertIn("MALLOC_ARENA_MAX", fix)
    
    def test_segfault_fix(self):
        engine = ErrorFeedbackEngine(use_model=False)
        fix = engine.process("buggy_program", "", "Segmentation fault (core dumped)", [])
        self.assertIn("OMP_NUM_THREADS", fix)
    
    def test_disk_full_fix(self):
        engine = ErrorFeedbackEngine(use_model=False)
        fix = engine.process("write_file", "", "No space left on device", [])
        self.assertIn("rm -rf", fix)
    
    def test_summary(self):
        engine = ErrorFeedbackEngine(use_model=False)
        engine.process("cmd1", "", "error1", [])
        engine.process("cmd2", "", "error2", [])
        summary = engine.get_summary()
        self.assertEqual(summary["total_errors"], 2)
        self.assertEqual(summary["unresolved"], 2)


if __name__ == "__main__":
    unittest.main()
