"""
TTL Cache
=========
Simple in-process cache with time-to-live expiration.
No external dependency (no Redis needed for v2).

Used primarily for web search result caching to avoid
re-fetching identical queries within the TTL window.
"""

import hashlib
import time
from typing import Any, Optional


class TTLCache:
    """In-process cache with per-key TTL expiration."""

    def __init__(self, default_ttl: int = 3600):
        self._store: dict[str, tuple[Any, float]] = {}
        self._ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        """Get a value by key. Returns None if expired or missing."""
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: int = None) -> None:
        """Set a value with optional custom TTL."""
        self._store[key] = (value, time.time() + (ttl or self._ttl))

    def invalidate(self, key: str) -> None:
        """Remove a specific key."""
        self._store.pop(key, None)

    def clear(self) -> None:
        """Remove all entries."""
        self._store.clear()

    @staticmethod
    def hash_key(*args) -> str:
        """Create a deterministic hash key from arguments."""
        return hashlib.sha256(str(args).encode()).hexdigest()[:16]

    @property
    def size(self) -> int:
        return len(self._store)


# Singleton instances used across the application
search_cache = TTLCache(default_ttl=3600)     # 1 hour for web search results
embedding_cache = TTLCache(default_ttl=7200)  # 2 hours for embeddings
llm_response_cache = TTLCache(default_ttl=1800)  # 30 min for identical LLM prompts (retries)
