"""Caching system for TTS audio data."""

from pathlib import Path
from typing import Any

import diskcache
import platformdirs


class TTSCache:
    """LRU cache for TTS audio data with disk persistence."""

    def __init__(
        self,
        enabled: bool = True,
        cache_dir: Path | None = None,
        max_size_mb: int = 10000,
        max_items: int = 1000,
    ):
        self.enabled = enabled
        self.max_size_mb = max_size_mb
        self.max_items = max_items

        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path(platformdirs.user_cache_dir("gensay", "gensay"))

        self.cache_dir.mkdir(parents=True, exist_ok=True)

        if self.enabled:
            self._cache = diskcache.Cache(
                directory=str(self.cache_dir),
                size_limit=max_size_mb * 1024 * 1024,
                eviction_policy="least-recently-used",
                cull_limit=min(100, max_items // 10),
            )
            self._cache.stats(enable=True)

    def get(self, key: str) -> bytes | None:
        """Get audio data from cache."""
        if not self.enabled:
            return None

        return self._cache.get(key)

    def put(self, key: str, data: bytes) -> None:
        """Store audio data in cache."""
        if not self.enabled:
            return

        self._cache[key] = data

    def clear(self) -> None:
        """Clear all cached data."""
        if not self.enabled:
            return

        self._cache.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        if not self.enabled:
            return {
                "enabled": False,
                "items": 0,
                "size_mb": 0,
                "max_size_mb": self.max_size_mb,
                "max_items": self.max_items,
                "cache_dir": str(self.cache_dir),
                "hits": 0,
                "misses": 0,
            }

        hits, misses = self._cache.stats()

        return {
            "enabled": self.enabled,
            "items": len(self._cache),
            "size_mb": self._cache.volume() / (1024 * 1024),
            "max_size_mb": self.max_size_mb,
            "max_items": self.max_items,
            "cache_dir": str(self.cache_dir),
            "hits": hits,
            "misses": misses,
        }
