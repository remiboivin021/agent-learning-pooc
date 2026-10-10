"""MCP server exposing the engineering brain to agents (streamable HTTP)."""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from . import store

mcp = FastMCP("engineering-brain", host=os.environ.get("HOST", "0.0.0.0"),
              port=int(os.environ.get("PORT", "8000")))


@mcp.tool()
def search_lessons(query: str, limit: int = 5, kind: str | None = None,
                   tags: list[str] | None = None, repo: str | None = None) -> list[dict]:
    """Find engineering lessons relevant to a task.

    Describe the situation in natural language. Results carry a `status`
    (candidate, validated, contested): treat candidate and contested lessons as
    hypotheses to check, not as rules.
    """
    return store.search_lessons(query, limit, kind, tags, repo)


@mcp.tool()
def get_lesson(lesson_id: str) -> dict | None:
    """Return one lesson with its evidence and sources."""
    return store.get_lesson(lesson_id)


def store_lesson(lesson: dict, repository: str, pull_request: int, last_sha: str) -> dict:
    """Store a candidate lesson extracted from a merged PR.

    Always stored as `candidate`; near-duplicates add a source to the existing lesson.
    """
    return store.store_lesson(lesson, {"repository": repository,
                                       "pull_request": pull_request, "last_sha": last_sha})


def mark_lessons_contested(repository: str, pull_request: int) -> dict:
    """Flag lessons that came from a PR later reverted or hot-fixed."""
    return store.mark_lessons_contested(repository, pull_request)


# Agents that consume lessons must not be able to write them: writes come from the
# post-merge extraction job only (python -m app.ingest). Opt in with BRAIN_WRITE_TOOLS=1.
if os.environ.get("BRAIN_WRITE_TOOLS") == "1":
    mcp.tool()(store_lesson)
    mcp.tool()(mark_lessons_contested)


def main() -> None:
    store.wait_and_init()
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
