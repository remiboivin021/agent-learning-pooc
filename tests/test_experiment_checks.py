"""Each experiment check must fail on the defective code and pass on a reference fix.

Without this the A/B experiment could not tell a fix from a non-fix.
Run with: python3 -m unittest discover -s tests
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TASKS = Path(__file__).resolve().parent.parent / "experiments" / "tasks"

FIXES = {
    "bool_int": ("volume.py", '''def set_volume(level):
    if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= 100:
        raise ValueError("level must be an integer between 0 and 100")
    return level
'''),
    "error_type": ("colors.py", '''NAMED = {"red", "green", "blue"}


def parse_color(value):
    if not isinstance(value, str):
        raise TypeError("color must be a string")
    if value not in NAMED:
        raise ValueError(f"unknown color: {value!r}")
    return value
'''),
    "stdout_reconfig": ("textout.py", '''import sys


def greet(name):
    print(f"héllo {name}")
'''),
    "utf8_detect": ("detect.py", '''import sys


def supports_utf8():
    encoding = getattr(sys.stdout, "encoding", None)
    return bool(encoding) and encoding.lower().replace("_", "-") in ("utf-8", "utf8")
'''),
    "push_trigger": ("ci.yml", '''name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python3 -m unittest discover -s tests
'''),
}


def run_check(task: str, fix=None) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        for item in (TASKS / task).iterdir():
            if item.name not in ("check.py", "prompt.txt"):
                shutil.copy(item, tmp)
        if fix:
            Path(tmp, fix[0]).write_text(fix[1])
        return subprocess.run([sys.executable, str(TASKS / task / "check.py")], cwd=tmp,
                              capture_output=True, text=True, timeout=60,
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


class ExperimentChecksTest(unittest.TestCase):
    def test_every_task_has_a_reference_fix(self):
        self.assertEqual({p.name for p in TASKS.iterdir()}, set(FIXES))

    def test_defective_code_fails_the_check(self):
        for task in FIXES:
            with self.subTest(task=task):
                self.assertNotEqual(run_check(task).returncode, 0)

    def test_reference_fix_passes_the_check(self):
        for task, fix in FIXES.items():
            with self.subTest(task=task):
                result = run_check(task, fix)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
