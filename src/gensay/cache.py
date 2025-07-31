"""Caching system for TTS audio data."""

import json
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import platformdirs


class TTSCache:
    """LRU cache for TTS audio data with disk persistence."""

    def __init__(
        self,
        enabled: bool = True,
        cache_dir: Path | None = None,
        max_size_mb: int = 500,
        max_items: int = 1000,
    ):
        self.enabled = enabled
        self.max_size_mb = max_size_mb
        self.max_items = max_items

        # Setup cache directory
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path(platformdirs.user_cache_dir("gensay", "gensay"))

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.cache_dir / "cache_index.json"

        # In-memory LRU cache
        self._memory_cache: OrderedDict[str, bytes] = OrderedDict()
        self._disk_index: dict[str, dict[str, Any]] = {}

        # Load existing cache index
        if self.enabled:
            self._load_index()

    def get(self, key: str) -> bytes | None:
        """Get audio data from cache."""
        if not self.enabled:
            return None

        # Check memory cache first
        if key in self._memory_cache:
            # Move to end (most recently used)
            self._memory_cache.move_to_end(key)
            return self._memory_cache[key]

        # Check disk cache
        if key in self._disk_index:
            file_path = self.cache_dir / f"{key}.audio"
            if file_path.exists():
                try:
                    data = file_path.read_bytes()
                    # Update memory cache
                    self._memory_cache[key] = data
                    self._memory_cache.move_to_end(key)
                    # Update access time
                    self._disk_index[key]["last_access"] = time.time()
                    return data
                except Exception:
                    # Remove corrupt entry
                    del self._disk_index[key]
                    file_path.unlink(missing_ok=True)

        return None

    def put(self, key: str, data: bytes) -> None:
        """Store audio data in cache."""
        if not self.enabled:
            return

        # Add to memory cache
        self._memory_cache[key] = data
        self._memory_cache.move_to_end(key)

        # Limit memory cache size
        while len(self._memory_cache) > 100:  # Keep last 100 in memory
            self._memory_cache.popitem(last=False)

        # Save to disk
        file_path = self.cache_dir / f"{key}.audio"
        try:
            file_path.write_bytes(data)
            self._disk_index[key] = {
                "size": len(data),
                "created": time.time(),
                "last_access": time.time(),
            }
            self._save_index()
            self._evict_if_needed()
        except Exception as e:
            print(f"Failed to cache audio: {e}")

    def clear(self) -> None:
        """Clear all cached data."""
        self._memory_cache.clear()
        self._disk_index.clear()

        # Remove all cache files
        for file in self.cache_dir.glob("*.audio"):
            file.unlink(missing_ok=True)

        self._save_index()

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total_size = sum(entry["size"] for entry in self._disk_index.values())
        return {
            "enabled": self.enabled,
            "items": len(self._disk_index),
            "size_mb": total_size / (1024 * 1024),
            "max_size_mb": self.max_size_mb,
            "max_items": self.max_items,
            "cache_dir": str(self.cache_dir),
        }

    def _load_index(self) -> None:
        """Load cache index from disk."""
        if self.index_file.exists():
            try:
                with open(self.index_file) as f:
                    self._disk_index = json.load(f)
            except Exception:
                self._disk_index = {}

    def _save_index(self) -> None:
        """Save cache index to disk."""
        try:
            with open(self.index_file, "w") as f:
                json.dump(self._disk_index, f, indent=2)
        except Exception as e:
            print(f"Failed to save cache index: {e}")

    def _evict_if_needed(self) -> None:
        """Evict old entries if cache is too large."""
        # Check size limit
        total_size = sum(entry["size"] for entry in self._disk_index.values())
        if total_size > self.max_size_mb * 1024 * 1024:
            self._evict_lru(total_size)

        # Check item limit
        if len(self._disk_index) > self.max_items:
            self._evict_lru()

    def _evict_lru(self, current_size: int | None = None) -> None:
        """Evict least recently used items."""
        # Sort by last access time
        sorted_items = sorted(self._disk_index.items(), key=lambda x: x[1]["last_access"])

        # Remove oldest items
        target_size = self.max_size_mb * 1024 * 1024 * 0.8  # 80% of max
        removed = 0

        for key, entry in sorted_items:
            if current_size and current_size < target_size:
                break
            if len(self._disk_index) - removed <= self.max_items * 0.8:
                break

            # Remove file
            file_path = self.cache_dir / f"{key}.audio"
            file_path.unlink(missing_ok=True)

            # Update size
            if current_size:
                current_size -= entry["size"]

            # Remove from index
            del self._disk_index[key]
            removed += 1

        if removed > 0:
            self._save_index()
