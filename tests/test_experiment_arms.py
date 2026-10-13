"""Run with: python3 -m unittest discover -s tests"""
import os
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "experiments"))

import run  # noqa: E402


class ArmsTest(unittest.TestCase):
    def test_only_forced_arm_orders_a_search(self):
        self.assertEqual(run.arm_prompt("base", "task"), "task")
        self.assertEqual(run.arm_prompt("brain", "task"), "task")
        forced = run.arm_prompt("forced", "task")
        self.assertIn("brain_search_lessons", forced)
        self.assertTrue(forced.endswith("task"))

    def test_base_has_no_mcp_others_have_brain(self):
        self.assertEqual(run.arm_config("base")["mcp"], {})
        for arm in ("brain", "forced"):
            self.assertIn("brain", run.arm_config(arm)["mcp"])

    def test_every_arm_denies_bash(self):
        for arm in run.ARMS:
            self.assertEqual(run.arm_config(arm)["permission"]["bash"], "deny")


if __name__ == "__main__":
    unittest.main()
