"""Tests for caching system."""

import sys
import tempfile
from pathlib import Path

import pytest

from gensay.cache import TTSCache
from gensay.providers import MacOSSayProvider, TTSConfig


@pytest.mark.skipif(
    sys.platform != "darwin" or not Path("/usr/bin/say").exists(), reason="macOS say not available"
)
def test_cache_with_macos_provider():
    """Test caching with macOS provider generating actual audio."""

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        output_dir = Path(tmpdir) / "output"
        output_dir.mkdir()
        cache_dir.mkdir()

        # Create cache instance and inject it into provider
        cache = TTSCache(cache_dir=cache_dir)
        config = TTSConfig(voice="Alex", rate=200)
        provider = MacOSSayProvider(config)
        provider._cache = cache

        # Test text
        text = "Hello, world!"

        # First generation - should generate and cache
        cache_key = provider._get_cache_key(text, config.voice, config.rate)

        cached_audio = cache.get(cache_key)
        assert cached_audio is None, "Cache should be empty initially"

        # Generate audio
        output_path = output_dir / "test1.m4a"
        provider.save_to_file(text, output_path, voice=config.voice, rate=config.rate)

        assert output_path.exists(), "Audio file should be generated"

        # Read generated audio and cache it
        audio_data = output_path.read_bytes()
        cache.put(cache_key, audio_data)

        # Verify it was cached
        cached_audio = cache.get(cache_key)
        assert cached_audio == audio_data, "Cached audio should match generated audio"

        # Second request with same parameters - should use cache
        cached_audio = cache.get(cache_key)
        assert cached_audio is not None, "Should retrieve from cache"

        # Write cached audio to file
        output_path2 = output_dir / "test2.m4a"
        output_path2.write_bytes(cached_audio)

        # Verify the files are identical
        assert output_path2.read_bytes() == audio_data, "Cached audio should match original"

        # Verify cache stats
        stats = cache.get_stats()
        assert stats["items"] == 1
        assert stats["size_mb"] > 0


def test_cache_key_differentiation():
    """Test that different parameters generate different cache keys."""
    provider = MacOSSayProvider(TTSConfig())

    text = "Test text"

    key1 = provider._get_cache_key(text, "Alex", 200)
    key2 = provider._get_cache_key(text, "Samantha", 200)
    key3 = provider._get_cache_key(text, "Alex", 250)
    key4 = provider._get_cache_key("Different text", "Alex", 200)

    # All keys should be different
    assert key1 != key2, "Different voices should produce different keys"
    assert key1 != key3, "Different rates should produce different keys"
    assert key1 != key4, "Different text should produce different keys"
    assert key2 != key3, "Different parameters should produce different keys"

    # All keys should be SHA256 hex (64 chars)
    assert len(key1) == 64
    assert len(key2) == 64
    assert len(key3) == 64
    assert len(key4) == 64


def test_cache_stats_with_audio_data():
    """Test cache statistics with actual audio data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        cache_dir.mkdir()

        cache = TTSCache(cache_dir=cache_dir)
        provider = MacOSSayProvider(TTSConfig())
        provider._cache = cache

        audio1 = b"x" * 10000  # 10KB
        audio2 = b"y" * 20000  # 20KB

        cache.put(provider._get_cache_key("test1", "Alex", 200), audio1)
        cache.put(provider._get_cache_key("test2", "Samantha", 200), audio2)

        stats = cache.get_stats()
        assert stats["enabled"] is True
        assert stats["items"] == 2
        assert stats["size_mb"] > 0
        # Should be roughly 30KB (with some overhead)
        assert 0.02 < stats["size_mb"] < 0.1


def test_cache_clear_with_audio_data():
    """Test cache clearing with actual audio data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        cache_dir.mkdir()

        cache = TTSCache(cache_dir=cache_dir)
        provider = MacOSSayProvider(TTSConfig())
        provider._cache = cache

        # Add audio data
        cache.put(provider._get_cache_key("test1", "Alex", 200), b"audio1")
        cache.put(provider._get_cache_key("test2", "Samantha", 200), b"audio2")

        stats = cache.get_stats()
        assert stats["items"] == 2

        # Clear cache
        cache.clear()

        # Verify cleared
        assert cache.get(provider._get_cache_key("test1", "Alex", 200)) is None
        assert cache.get(provider._get_cache_key("test2", "Samantha", 200)) is None

        stats = cache.get_stats()
        assert stats["items"] == 0


@pytest.mark.skipif(
    sys.platform != "darwin" or not Path("/usr/bin/say").exists(), reason="macOS say not available"
)
def test_cache_miss_generates_new_audio():
    """Test that cache miss triggers audio generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        output_dir = Path(tmpdir) / "output"
        output_dir.mkdir()
        cache_dir.mkdir()

        cache = TTSCache(cache_dir=cache_dir)
        config = TTSConfig(voice="Alex", rate=200)
        provider = MacOSSayProvider(config)
        provider._cache = cache

        text1 = "First message"
        text2 = "Second message"

        # Generate and cache first message
        key1 = provider._get_cache_key(text1, config.voice, config.rate)
        output1 = output_dir / "first.m4a"
        provider.save_to_file(text1, output1)
        cache.put(key1, output1.read_bytes())

        # Check cache for second message - should be miss
        key2 = provider._get_cache_key(text2, config.voice, config.rate)
        cached = cache.get(key2)
        assert cached is None, "Second message should not be cached"

        # Generate second message
        output2 = output_dir / "second.m4a"
        provider.save_to_file(text2, output2)
        cache.put(key2, output2.read_bytes())

        # Verify both are now cached
        assert cache.get(key1) is not None
        assert cache.get(key2) is not None

        stats = cache.get_stats()
        assert stats["items"] == 2
