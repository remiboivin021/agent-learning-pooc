"""Ingest a lessons.json (from analyze.py) read on stdin: python -m app.ingest < lessons.json"""
from __future__ import annotations

import json
import sys

from . import store


def main() -> int:
    data = json.load(sys.stdin)
    store.wait_and_init()
    source = {"repository": data["repository"], "pull_request": data["pull_request"],
              "last_sha": data["last_sha"]}
    for lesson in data.get("lessons", []):
        result = store.store_lesson(lesson, source)
        print(json.dumps({"title": lesson["title"], **result}))
    print(f"{len(data.get('lessons', []))} lessons processed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
