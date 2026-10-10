#!/usr/bin/env python3
"""Build context.json for a merged PR: metadata, review threads, commits, ranked diffs.

Stdlib only. No LLM call. Inputs come from env (INPUT_* set by action.yml).
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
TOKEN_BUDGET = int(os.environ.get("INPUT_TOKEN_BUDGET", "60000"))
CHARS_PER_TOKEN = 4
MAX_PATCH_LINES = 400

IGNORED_GLOBS = [
    "*.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "go.sum", "Cargo.lock", "vendor/*", "*/vendor/*", "dist/*", "*/dist/*",
    "node_modules/*", "*.min.js", "*.min.css", "*.snap", "*.pb.go", "*_pb2.py",
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.pdf", "*.zip", "*.ico", "*.woff*",
]

SECRET_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{40,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"),
]


def redact(text: str | None) -> str:
    out = text or ""
    for pat in SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


def request(path: str, token: str) -> tuple[object, dict]:
    url = path if path.startswith("http") else f"{API}{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp), dict(resp.headers)
        except urllib.error.HTTPError as err:
            retryable = err.code in (429, 500, 502, 503) or (
                err.code == 403 and err.headers.get("Retry-After"))
            if not retryable or attempt == 3:
                raise
            time.sleep(int(err.headers.get("Retry-After", 2 ** attempt)))
    raise RuntimeError("unreachable")


def paginate(path: str, token: str) -> list:
    items: list = []
    url = f"{API}{path}{'&' if '?' in path else '?'}per_page=100"
    while url:
        page, headers = request(url, token)
        items.extend(page)  # type: ignore[arg-type]
        match = re.search(r'<([^>]+)>;\s*rel="next"', headers.get("Link", ""))
        url = match.group(1) if match else ""
    return items


def is_bot(user: dict | None) -> bool:
    return bool(user) and (user.get("type") == "Bot" or user.get("login", "").endswith("[bot]"))


def is_ignored(filename: str) -> bool:
    return any(fnmatch.fnmatch(filename, g) for g in IGNORED_GLOBS)


def truncate_patch(patch: str) -> str:
    lines = patch.splitlines()
    if len(lines) <= MAX_PATCH_LINES:
        return patch
    dropped = len(lines) - MAX_PATCH_LINES
    return "\n".join(lines[:MAX_PATCH_LINES]) + f"\n[TRUNCATED {dropped} lines]"


def set_output(key: str, value: str) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a") as fh:
            fh.write(f"{key}={value}\n")


def skip(reason: str, out_path: Path) -> int:
    out_path.write_text(json.dumps({"skipped": True, "reason": reason}, indent=2))
    print(f"skipped: {reason}")
    set_output("skipped", "true")
    return 0


def resolve_pr_number() -> int:
    explicit = os.environ.get("INPUT_PR_NUMBER", "").strip()
    if explicit:
        return int(explicit)
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path and Path(event_path).exists():
        event = json.loads(Path(event_path).read_text())
        if "pull_request" in event:
            return int(event["pull_request"]["number"])
    raise SystemExit("no PR number: set pr_number or run on pull_request event")


def main() -> int:
    token = os.environ.get("INPUT_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("INPUT_REPOSITORY") or os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        raise SystemExit("GITHUB_TOKEN and repository are required")
    out_path = Path(os.environ.get("INPUT_OUTPUT_PATH", "context.json"))
    number = resolve_pr_number()

    pr, _ = request(f"/repos/{repo}/pulls/{number}", token)
    assert isinstance(pr, dict)
    if not pr.get("merged"):
        return skip("PR not merged", out_path)
    if is_bot(pr.get("user")):
        return skip("PR authored by bot", out_path)
    title = pr.get("title", "")
    if title.startswith("Revert "):
        return skip("revert PR", out_path)

    last = pr["head"]["sha"]
    # base.sha is the base tip, not the merge-base: resolve the real one via compare.
    compare, _ = request(f"/repos/{repo}/compare/{pr['base']['sha']}...{last}", token)
    base = compare["merge_base_commit"]["sha"]  # type: ignore[index]

    commits = [c for c in paginate(f"/repos/{repo}/pulls/{number}/commits", token)
               if len(c.get("parents", [])) <= 1]
    first = commits[0]["sha"] if commits else last

    reviews = paginate(f"/repos/{repo}/pulls/{number}/reviews", token)
    inline = paginate(f"/repos/{repo}/pulls/{number}/comments", token)
    issue_comments = paginate(f"/repos/{repo}/issues/{number}/comments", token)
    files = paginate(f"/repos/{repo}/pulls/{number}/files", token)

    commented_paths = {c["path"] for c in inline if not is_bot(c.get("user"))}
    first_review_at = min((r["submitted_at"] for r in reviews if r.get("submitted_at")), default=None)
    late_shas = {c["sha"] for c in commits
                 if first_review_at and c["commit"]["committer"]["date"] > first_review_at}

    def rank(f: dict) -> int:
        if f["filename"] in commented_paths:
            return 0
        if re.search(r"(^|/)(test|tests|__tests__)/|_test\.|\.test\.|\.spec\.", f["filename"]):
            return 3
        return 2

    kept, ignored = [], []
    for f in sorted(files, key=lambda f: (rank(f), f["filename"])):
        (ignored if is_ignored(f["filename"]) or "patch" not in f else kept).append(f)

    budget_chars = TOKEN_BUDGET * CHARS_PER_TOKEN
    used = 0
    diffs, dropped = [], []
    for f in kept:
        patch = redact(truncate_patch(f["patch"]))
        if used + len(patch) > budget_chars:
            dropped.append(f["filename"])
            continue
        used += len(patch)
        diffs.append({"file": f["filename"], "status": f["status"],
                      "additions": f["additions"], "deletions": f["deletions"],
                      "commented": f["filename"] in commented_paths, "patch": patch})

    context = {
        "skipped": False,
        "repository": repo,
        "pull_request": number,
        "meta": {
            "title": redact(title), "body": redact(pr.get("body")),
            "author": pr["user"]["login"],
            "labels": [l["name"] for l in pr.get("labels", [])],
            "merge_commit_sha": pr.get("merge_commit_sha"),
            "first_sha": first, "last_sha": last, "base_sha": base,
        },
        "review_threads": [
            {"id": c["id"], "reply_to": c.get("in_reply_to_id"), "path": c["path"],
             "line": c.get("line") or c.get("original_line"), "user": c["user"]["login"],
             "diff_hunk": redact(c.get("diff_hunk")), "body": redact(c["body"])}
            for c in inline if not is_bot(c.get("user"))],
        "reviews": [
            {"user": r["user"]["login"], "state": r["state"], "body": redact(r.get("body"))}
            for r in reviews if not is_bot(r.get("user")) and (r.get("body") or r["state"] != "COMMENTED")],
        "issue_comments": [
            {"user": c["user"]["login"], "body": redact(c["body"])}
            for c in issue_comments if not is_bot(c.get("user"))],
        "commits": [
            {"sha": c["sha"], "message": redact(c["commit"]["message"]),
             "after_first_review": c["sha"] in late_shas}
            for c in commits],
        "diffs": diffs,
        "diff_stat": [{"file": f["filename"], "additions": f["additions"],
                       "deletions": f["deletions"]} for f in files],
        "omitted": {"ignored": [f["filename"] for f in ignored], "over_budget": dropped},
    }
    out_path.write_text(json.dumps(context, indent=2))
    print(f"wrote {out_path}: {len(diffs)} diffs, {len(context['review_threads'])} review comments")
    set_output("skipped", "false")
    set_output("context_path", str(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
