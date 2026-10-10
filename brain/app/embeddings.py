from __future__ import annotations

import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.request

from . import config

FAKE_DIM = 256


def lesson_text(lesson: dict) -> str:
    """Textual representation embedded for a lesson (not the raw diff)."""
    parts = [
        ("Kind", lesson.get("kind", "")),
        ("Title", lesson.get("title", "")),
        ("Problem", lesson.get("problem", "")),
        ("Lesson", lesson.get("rule", "")),
        ("Solution", lesson.get("solution", "")),
        ("Reasoning", lesson.get("reasoning", "")),
        ("Tags", ", ".join(lesson.get("tags", []))),
    ]
    return "\n\n".join(f"{name}:\n{value}" for name, value in parts if value)


def _fake(text: str) -> list[float]:
    vec = [0.0] * FAKE_DIM
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        digest = hashlib.sha256(token.encode()).digest()
        vec[int.from_bytes(digest[:4], "big") % FAKE_DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _openrouter(texts: list[str]) -> list[list[float]]:
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is required when EMBEDDING_PROVIDER=openrouter")
    body = json.dumps({"model": config.EMBEDDING_MODEL, "input": texts}).encode()
    req = urllib.request.Request(
        f"{config.OPENROUTER_URL}/embeddings", data=body, method="POST",
        headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
                 "Content-Type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.load(resp)["data"]
            return [item["embedding"] for item in sorted(data, key=lambda d: d["index"])]
        except urllib.error.HTTPError as err:
            # Free models rate-limit: back off on 429/5xx.
            if err.code not in (429, 500, 502, 503) or attempt == 3:
                raise RuntimeError(f"embedding request failed: HTTP {err.code}") from err
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError("unreachable")


def embed(texts: list[str]) -> list[list[float]]:
    if config.EMBEDDING_PROVIDER == "fake":
        return [_fake(t) for t in texts]
    return _openrouter(texts)
