#!/bin/sh
set -eu

python3 /app/extract.py

# Analysis is optional: without a key, only context.json is produced.
if [ -z "${INPUT_OPENROUTER_API_KEY:-}" ]; then
  echo "no openrouter_api_key provided, skipping analysis"
  exit 0
fi

export OPENROUTER_API_KEY="$INPUT_OPENROUTER_API_KEY"
exec python3 /app/analyze.py
