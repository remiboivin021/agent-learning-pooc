import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://brain:brain@postgres:5432/brain")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333").rstrip("/")
COLLECTION = os.environ.get("QDRANT_COLLECTION", "lessons")

# "openrouter" for real embeddings, "fake" for offline tests (hashed bag of words).
EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "openrouter")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "nvidia/nemotron-3-embed-1b:free")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = os.environ.get("OPENROUTER_URL", "https://openrouter.ai/api/v1")

# Cosine similarity above which a new lesson is a duplicate of a stored one.
DEDUP_THRESHOLD = float(os.environ.get("DEDUP_THRESHOLD", "0.92"))

# Above this (but below DEDUP_THRESHOLD) a new lesson is stored as its own lesson
# and reported with `similar_to` so a curator can decide whether to merge.
SIMILAR_THRESHOLD = float(os.environ.get("SIMILAR_THRESHOLD", "0.5"))
