"""Postgres (source of truth) + Qdrant (vectors) storage for lessons.

Rules enforced here:
- New lessons are always `candidate`. Nothing in this module promotes a lesson
  to `validated`; that is reserved for the statistical job.
- Storing is idempotent per (repository, pull_request, last_sha, title).
- A near-duplicate adds a source to the existing lesson instead of a new one.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid

import psycopg
from psycopg.types.json import Jsonb

from . import config, embeddings

SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons (
  id uuid PRIMARY KEY,
  status text NOT NULL DEFAULT 'candidate',
  confidence real,
  kind text NOT NULL,
  title text NOT NULL,
  body jsonb NOT NULL,
  repo text NOT NULL,
  pr integer NOT NULL,
  last_sha text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (repo, pr, last_sha, title)
);
CREATE TABLE IF NOT EXISTS lesson_sources (
  lesson_id uuid NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
  repo text NOT NULL,
  pr integer NOT NULL,
  last_sha text NOT NULL,
  PRIMARY KEY (lesson_id, repo, pr, last_sha)
);
CREATE INDEX IF NOT EXISTS lessons_origin ON lessons (repo, pr);
"""

_collection_ready = False


def connect() -> psycopg.Connection:
    return psycopg.connect(config.DATABASE_URL)


def wait_and_init(timeout: int = 60) -> None:
    deadline = time.time() + timeout
    while True:
        try:
            with connect() as conn:
                conn.execute(SCHEMA)
            _q("GET", "/collections")
            return
        except (psycopg.OperationalError, urllib.error.URLError, ConnectionError):
            if time.time() > deadline:
                raise
            time.sleep(2)


def _q(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{config.QDRANT_URL}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _ensure_collection(dim: int) -> None:
    global _collection_ready
    if _collection_ready:
        return
    try:
        _q("GET", f"/collections/{config.COLLECTION}")
    except urllib.error.HTTPError as err:
        if err.code != 404:
            raise
        _q("PUT", f"/collections/{config.COLLECTION}",
           {"vectors": {"size": dim, "distance": "Cosine"}})
    _collection_ready = True


def store_lesson(lesson: dict, source: dict) -> dict:
    repo, pr, sha = source["repository"], int(source["pull_request"]), source["last_sha"]
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM lessons WHERE repo=%s AND pr=%s AND last_sha=%s AND title=%s",
            (repo, pr, sha, lesson["title"])).fetchone()
        if row:
            return {"id": str(row[0]), "created": False, "reason": "already stored"}

        vector = embeddings.embed([embeddings.lesson_text(lesson)])[0]
        _ensure_collection(len(vector))
        hits = _q("POST", f"/collections/{config.COLLECTION}/points/search",
                  {"vector": vector, "limit": 1, "with_payload": False})["result"]
        if hits and hits[0]["score"] >= config.DEDUP_THRESHOLD:
            existing = hits[0]["id"]
            conn.execute(
                "INSERT INTO lesson_sources VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (existing, repo, pr, sha))
            return {"id": existing, "created": False, "reason": "duplicate",
                    "similarity": round(hits[0]["score"], 4)}

        lesson_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO lessons (id, confidence, kind, title, body, repo, pr, last_sha) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (lesson_id, lesson.get("confidence"), lesson["kind"], lesson["title"],
             Jsonb(lesson), repo, pr, sha))
        conn.execute("INSERT INTO lesson_sources VALUES (%s,%s,%s,%s)",
                     (lesson_id, repo, pr, sha))
        # Qdrant last: if it fails, the Postgres transaction rolls back.
        _q("PUT", f"/collections/{config.COLLECTION}/points?wait=true", {"points": [{
            "id": lesson_id, "vector": vector,
            "payload": {"kind": lesson["kind"], "tags": lesson.get("tags", []),
                        "status": "candidate", "repo": repo}}]})
        return {"id": lesson_id, "created": True}


def _view(row: tuple, score: float | None = None) -> dict:
    lesson_id, status, confidence, body, sources = row
    out = {"id": str(lesson_id), "status": status, "confidence": confidence,
           "kind": body["kind"], "title": body["title"], "rule": body["rule"],
           "problem": body["problem"], "solution": body["solution"],
           "reasoning": body["reasoning"], "tags": body.get("tags", []),
           "evidence": body.get("evidence", {}), "sources": sources}
    if score is not None:
        out["score"] = round(score, 4)
    return out


_SELECT = """
SELECT l.id, l.status, l.confidence, l.body,
       COALESCE((SELECT jsonb_agg(jsonb_build_object('repo', s.repo, 'pr', s.pr))
                 FROM lesson_sources s WHERE s.lesson_id = l.id), '[]'::jsonb)
FROM lessons l WHERE l.id = ANY(%s::uuid[])
"""


def search_lessons(query: str, limit: int = 5, kind: str | None = None,
                   tags: list[str] | None = None, repo: str | None = None) -> list[dict]:
    vector = embeddings.embed([query])[0]
    _ensure_collection(len(vector))
    must = []
    if kind:
        must.append({"key": "kind", "match": {"value": kind}})
    if tags:
        must.append({"key": "tags", "match": {"any": tags}})
    if repo:
        must.append({"key": "repo", "match": {"value": repo}})
    flt = {"must": must, "must_not": [{"key": "status", "match": {"value": "deprecated"}}]}
    hits = _q("POST", f"/collections/{config.COLLECTION}/points/search",
              {"vector": vector, "limit": max(1, min(limit, 20)), "filter": flt})["result"]
    if not hits:
        return []
    scores = {h["id"]: h["score"] for h in hits}
    with connect() as conn:
        rows = conn.execute(_SELECT, (list(scores),)).fetchall()
    views = [_view(r, scores[str(r[0])]) for r in rows]
    return sorted(views, key=lambda v: -v["score"])


def get_lesson(lesson_id: str) -> dict | None:
    with connect() as conn:
        rows = conn.execute(_SELECT, ([lesson_id],)).fetchall()
    return _view(rows[0]) if rows else None


def mark_lessons_contested(repo: str, pr: int) -> dict:
    """Flag lessons that originate from a PR later found faulty (revert/hotfix)."""
    with connect() as conn:
        ids = [str(r[0]) for r in conn.execute(
            "UPDATE lessons SET status='contested' WHERE repo=%s AND pr=%s "
            "AND status IN ('candidate','validated') RETURNING id", (repo, pr)).fetchall()]
        if ids:
            _q("POST", f"/collections/{config.COLLECTION}/points/payload?wait=true",
               {"payload": {"status": "contested"}, "points": ids})
    return {"contested": ids}
