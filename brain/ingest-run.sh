#!/bin/sh
# Ingest the lessons.json artifact of a learn-from-pr run into the local brain.
# Usage: brain/ingest-run.sh <run-id> [owner/repo]
set -eu

RUN_ID=${1:?usage: ingest-run.sh <run-id> [owner/repo]}
REPO=${2:-remiboivin021/web-template}
HERE=$(cd "$(dirname "$0")" && pwd)

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

gh run download "$RUN_ID" -R "$REPO" -D "$TMP"
FILE=$(find "$TMP" -name lessons.json | head -1)
if [ -z "$FILE" ]; then
  echo "no lessons.json in run $RUN_ID (analysis skipped or failed?)" >&2
  exit 1
fi

# Brain stack must be running: cd brain && docker compose up -d
cd "$HERE"
docker compose exec -T brain python -m app.ingest < "$FILE"
