#!/usr/bin/env python3
"""A/B experiment: does the brain make OpenCode fix lesson-related defects?

For each task and repetition, run the agent on a copy of the defective code, per arm:
  - "base":   no MCP, no AGENTS.md
  - "brain":  MCP `brain` + AGENTS.md; the agent decides whether to search lessons
              (measures whether it does so on its own)
  - "forced": MCP `brain` + AGENTS.md + the task prompt orders a lesson search first
              (measures whether retrieved lessons help once they are actually used)
then run the task's check.py in the working copy. Results go to a JSONL file.
Compare base vs forced for usefulness; brain_called in the brain arm for propensity.

Usage: python3 experiments/run.py --out results.jsonl [--reps 3] [--tasks bool_int,...]
                                  [--arms base,brain,forced]
Needs OPENROUTER_API_KEY in the environment (e.g. `set -a; . brain/.env`).
Each run costs several model requests: mind the OpenRouter free quota.
Agent-written code is executed by check.py: run this in a disposable environment.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = Path(__file__).resolve().parent / "tasks"
DEFAULT_MODEL = "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
BRAIN_URL = "http://127.0.0.1:8000/mcp"
# Same containment in both arms: the agent edits files in its copy and nothing else.
BASE_PERMISSION = {"bash": "deny", "webfetch": "deny", "websearch": "deny",
                   "external_directory": "deny", "skill": "deny"}


ARMS = ("base", "brain", "forced")
FORCED_PREFIX = ("Before changing any code, call the brain_search_lessons tool with a short "
                 "description of this task, and read the results. Then do the task.\n\n")


def arm_prompt(arm: str, prompt: str) -> str:
    return FORCED_PREFIX + prompt if arm == "forced" else prompt


def arm_config(arm: str) -> dict:
    cfg = {"$schema": "https://opencode.ai/config.json", "permission": BASE_PERMISSION,
           "autoupdate": False, "share": "disabled", "mcp": {}}
    if arm != "base":
        cfg["mcp"] = {"brain": {"type": "remote", "url": BRAIN_URL, "enabled": True}}
    return cfg


def run_one(task: str, arm: str, model: str, timeout: int) -> dict:
    src = TASKS / task
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "work"
        work.mkdir()
        for item in src.iterdir():
            if item.name not in ("check.py", "prompt.txt"):
                shutil.copy(item, work / item.name)
        (work / "opencode.json").write_text(json.dumps(arm_config(arm)))
        if arm != "base":
            shutil.copy(ROOT / "AGENTS.md", work / "AGENTS.md")
        # PWD: OpenCode reads its project directory from $PWD, not from the process cwd.
        env = {**os.environ, "XDG_CONFIG_HOME": str(Path(tmp) / "xdg"), "PWD": str(work)}
        prompt = arm_prompt(arm, (src / "prompt.txt").read_text())
        started = time.time()
        try:
            agent = subprocess.run(
                ["opencode", "run", "--model", model, "--pure", "--format", "json", prompt],
                cwd=work, env=env, capture_output=True, text=True, timeout=timeout)
            output, error = agent.stdout, agent.stderr[-300:] if agent.returncode else ""
        except subprocess.TimeoutExpired:
            output, error = "", "timeout"
        # OpenCode exits 0 on provider errors: they only show up as events in the JSON stream.
        # A quota-exhausted run would be recorded as a failed fix, so stop instead.
        if "free_tier_daily" in output:
            raise SystemExit("OpenRouter free-tier daily quota exhausted: results would be "
                             "meaningless. Rerun after 00:00 UTC.")
        check = subprocess.run([sys.executable, str(src / "check.py")], cwd=work,
                               capture_output=True, text=True, timeout=60)
        return {
            "task": task, "arm": arm, "passed": check.returncode == 0,
            "check_message": (check.stderr or check.stdout).strip()[-200:],
            "brain_called": "brain_search_lessons" in output,
            "agent_error": error, "agent_tail": output[-800:], "seconds": round(time.time() - started, 1),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--tasks", default="")
    parser.add_argument("--arms", default=",".join(ARMS))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--pause", type=float, default=5.0)
    args = parser.parse_args()

    arms = [a for a in args.arms.split(",") if a]
    if any(a not in ARMS for a in arms):
        parser.error(f"unknown arm; choose from {ARMS}")
    if not os.environ.get("OPENROUTER_API_KEY"):
        parser.error("OPENROUTER_API_KEY missing: OpenCode would report 'Model not found'")
    names = [t for t in args.tasks.split(",") if t] or sorted(p.name for p in TASKS.iterdir())
    with open(args.out, "a") as out:
        for rep in range(args.reps):
            for task in names:
                for arm in arms:
                    row = {"rep": rep, **run_one(task, arm, args.model, args.timeout)}
                    out.write(json.dumps(row) + "\n")
                    out.flush()
                    print(f"{task:15} {arm:6} rep={rep} passed={row['passed']} "
                          f"brain_called={row['brain_called']} {row['agent_error']}")
                    time.sleep(args.pause)
    return 0


if __name__ == "__main__":
    sys.exit(main())
