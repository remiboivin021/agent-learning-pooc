# agent-learning-pooc

Self-learning loop for OpenCode: when a PR is merged, an agent extracts reusable
engineering lessons from the review, they are stored in a vector memory (the "brain")
behind an MCP server, and future OpenCode tasks retrieve them.

This is a proof of concept. Nothing here is validated on real volume yet.

## Layout

| Path | Role |
|---|---|
| `action.yml`, `Dockerfile`, `entrypoint.sh` | Docker GitHub Action: extract then analyse |
| `src/extract.py` | PR → `context.json` (stdlib only, GitHub REST API, secret redaction) |
| `src/analyze.py` | `context.json` → `lessons.json` via `opencode run`, validation + retries |
| `brain/` | MCP server (FastMCP, streamable HTTP) + Postgres + Qdrant, `docker compose` |
| `brain/ingest-run.sh` | Manual ingestion of a CI run's `lessons.json` into the local brain |
| `experiments/` | A/B tasks: does retrieving lessons make the agent fix defects? |
| `opencode.json`, `AGENTS.md` | OpenCode config and instructions for **consumers** of the brain |
| `.github/workflows/learn.yml` | Trigger workflow (merged PR or `workflow_dispatch`) |

`AGENTS.md` is for OpenCode, not for you. Do not merge it into this file.

## Commands

```
python3 -m unittest discover -s tests          # 24 tests, no network, no quota
cd brain && docker compose up -d --build       # brain on 127.0.0.1:8000/mcp
brain/ingest-run.sh <run-id> [owner/repo]      # needs gh auth and the brain running
python3 experiments/run.py --out r.jsonl --reps 1
```

Offline brain tests: `EMBEDDING_PROVIDER=fake` (hashed bag of words, dim 256).

## Rules that must hold

- Lessons are always stored `candidate`. Only a future statistical job may promote
  them. Extraction must never raise confidence of an existing lesson.
- The brain MCP is **read-only** for agents (`search_lessons`, `get_lesson`). Writes
  go through `app.ingest`. `BRAIN_WRITE_TOOLS=1` is an explicit opt-in.
- The analysis agent runs with every OpenCode tool denied, no MCP, and an empty
  `XDG_CONFIG_HOME`. Without that, user-level MCP servers (Notion) leak into runs.
- A lesson must cite a review comment on a file listed in `evidence.files`, and have a
  non-`project` scope. Do not loosen this to get more lessons.
- PR content is untrusted input. Never give the analysis agent tools or secrets.

## Gotchas learned the hard way

- Docker action build context is the **Dockerfile's directory**. The Dockerfile lives
  at the repo root so `COPY src/...` works. Do not move it back under `docker/`.
- `opencode run`: `--file` is an array option and swallows trailing positionals; and
  attached files make the model try to `Read` them. The prompt goes through **stdin**.
- `mcp` must stay pinned `<2`: v2 renamed `FastMCP`.
- OpenCode takes its project directory from **`$PWD`**, not the subprocess cwd. Passing
  `cwd=` alone silently loads the caller's `opencode.json` (bash allowed, brain MCP on).
  Always set `PWD` too (`agent_env`). The deny-all config was ineffective until this
  was found: a forced `bash` call created a file. Verify with a sentinel-file test,
  `opencode debug config` alone does not prove it.
- A private action cannot be used by a **public** repo. `web-template` (public) needs
  this repo public. Flip it back to private afterwards and the workflow there breaks.
- OpenRouter free tier: 50 requests/day account-wide, shared by chat and embeddings.
  Reset 00:00 UTC. A 429 mentioning `free-models-per-day` is this, not a bug.
- `opencode run` exits 0 on provider errors, including quota exhaustion; the error is
  only an event in the `--format json` stream. `experiments/run.py` aborts on
  `free_tier_daily`. Results gathered without this check were all counted as failed fixes.
- Free models are flaky: empty output, missing closing tag, trailing text. The parser
  and 3 retries absorb it; do not remove them.
- Embedding model `nvidia/nemotron-3-embed-1b:free` has dim 2048. Changing model
  means recreating the Qdrant collection.
- Dedup thresholds (`DEDUP_THRESHOLD=0.92`, `SIMILAR_THRESHOLD=0.5`) are guesses from
  3 pairs. A paraphrase scored 0.57; unrelated lessons ~0.1. Calibration needs ~150
  labelled pairs.

## Secrets and local state

- `OPENROUTER_API_KEY` lives in `brain/.env` (git-ignored) and in the
  `web-template` repository secret. Never print or commit it.
- Editors leave backups: `brain/.env~` contains a key. `*~` is git-ignored but delete it.
- The brain has no authentication. Keep it on loopback; add auth before exposing it.

## Conventions

- Files, comments, commits and PR text in English, normal prose. Chat style does not
  apply to anything written to disk.
- Commit messages: conventional prefix (`feat:`, `fix:`, `chore:`) and the
  `Co-Authored-By` trailer from the session.
- Tests accompany validation logic. New experiment tasks need a `check.py` that fails
  on the defect and passes on a reference fix (`tests/test_experiment_checks.py`).
- Stdlib only in `src/`: the action image should stay small.

## Known gaps

No automatic ingestion (brain is local, Actions cannot reach it), no validation job,
no A/B measurement yet, no pain scoring, no curator for `similar_to`, no force-push
history. Lesson quality on real PRs is roughly one third reusable, one third
project-specific, one third noise.
