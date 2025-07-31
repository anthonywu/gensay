"""Tests for caching system."""

import tempfile
from pathlib import Path

from gensay.cache import TTSCache


def test_cache_basic_operations():
    """Test basic cache get/put operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = TTSCache(cache_dir=Path(tmpdir))

        # Test put and get
        test_data = b"test audio data"
        cache.put("test_key", test_data)

        retrieved = cache.get("test_key")
        assert retrieved == test_data

        # Test missing key
        assert cache.get("missing_key") is None


def test_cache_disabled():
    """Test cache when disabled."""
    cache = TTSCache(enabled=False)

    cache.put("test_key", b"data")
    assert cache.get("test_key") is None


def test_cache_stats():
    """Test cache statistics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = TTSCache(cache_dir=Path(tmpdir))

        # Add some data
        cache.put("key1", b"x" * 1000)
        cache.put("key2", b"y" * 2000)

        stats = cache.get_stats()
        assert stats["enabled"] is True
        assert stats["items"] == 2
        assert stats["size_mb"] > 0


def test_cache_clear():
    """Test cache clearing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = TTSCache(cache_dir=Path(tmpdir))

        # Add data
        cache.put("key1", b"data1")
        cache.put("key2", b"data2")

        # Clear cache
        cache.clear()

        # Verify cleared
        assert cache.get("key1") is None
        assert cache.get("key2") is None

        stats = cache.get_stats()
        assert stats["items"] == 0
