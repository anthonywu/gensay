"""Integration tests for all TTS providers - validates providers work without cache.

This module tests each provider by:
1. Selecting 2 voices from the provider
2. Disabling cache (fresh generation)
3. Generating audio for each voice
4. Saving to tests/artifacts/{provider}/{voice}.{ext}
"""

import sys
from pathlib import Path

import pytest

from gensay.providers import (
    AmazonPollyProvider,
    AudioFormat,
    ChatterboxProvider,
    ElevenLabsProvider,
    MacOSSayProvider,
    MockProvider,
    OpenAIProvider,
    TTSConfig,
)

# Define test artifacts directory
TEST_ARTIFACTS_DIR = Path(__file__).parent / "artifacts"


@pytest.fixture
def artifacts_dir():
    """Create and return artifacts directory."""
    TEST_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    return TEST_ARTIFACTS_DIR


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS provider only available on macOS")
def test_macos_provider(artifacts_dir):
    """Test macOS provider with 2 voices."""
    config = TTSConfig(cache_enabled=False)
    provider = MacOSSayProvider(config)

    # Get 2 English voices (language format is "en_US", not "en-")
    voices = [v for v in provider.list_voices() if "en" in v.get("language", "").lower()][:2]
    assert len(voices) >= 2, "Need at least 2 English voices"

    provider_dir = artifacts_dir / "macos"
    provider_dir.mkdir(exist_ok=True)

    for voice in voices:
        voice_id = voice["id"]
        voice_name = voice.get("name", voice_id)
        output_path = provider_dir / f"{voice_id}.m4a"
        text = f"Hi this is {voice_name} from macOS"
        provider.save_to_file(text, output_path, voice=voice_id)

        assert output_path.exists(), f"Expected file {output_path} to be created"
        assert output_path.stat().st_size > 1000, "File should be non-empty"


def test_mock_provider(artifacts_dir):
    """Test mock provider with 2 voices."""
    config = TTSConfig(cache_enabled=False)
    provider = MockProvider(config)

    voices = provider.list_voices()[:2]

    provider_dir = artifacts_dir / "mock"
    provider_dir.mkdir(exist_ok=True)

    for voice in voices:
        voice_id = voice["id"]
        voice_name = voice.get("name", voice_id)
        output_path = provider_dir / f"{voice_id}.m4a"
        text = f"Hi this is {voice_name} from Mock"
        provider.save_to_file(text, output_path, voice=voice_id)

        assert output_path.exists(), f"Expected file {output_path} to be created"
        assert output_path.stat().st_size > 0, "File should be non-empty"


def _chatterbox_available() -> bool:
    """Check if chatterbox library is available."""
    try:
        from chatterbox.tts_turbo import ChatterboxTurboTTS  # noqa: F401

        return True
    except ImportError:
        return False


def _ffmpeg_libs_configured() -> bool:
    """Check if FFmpeg libraries are properly configured for TorchCodec."""
    import os

    if sys.platform != "darwin":
        return True  # Only macOS needs DYLD_LIBRARY_PATH

    from gensay.providers.chatterbox import _find_ffmpeg_lib_path

    lib_path = _find_ffmpeg_lib_path()
    if not lib_path:
        return True  # No FFmpeg found, let torchcodec handle it

    current = os.environ.get("DYLD_LIBRARY_PATH", "")
    return lib_path in current.split(":")


@pytest.mark.skipif(sys.platform != "darwin", reason="Chatterbox only tested on macOS")
@pytest.mark.skipif(not _chatterbox_available(), reason="Chatterbox library not installed")
@pytest.mark.skipif(
    not _ffmpeg_libs_configured(), reason="DYLD_LIBRARY_PATH not configured for FFmpeg"
)
def test_chatterbox_provider(artifacts_dir):
    """Test Chatterbox provider with available voices."""
    config = TTSConfig(cache_enabled=False)
    provider = ChatterboxProvider(config)

    voices = provider.list_voices()[:2]

    provider_dir = artifacts_dir / "chatterbox"
    provider_dir.mkdir(exist_ok=True)

    for voice in voices:
        voice_id = voice["id"]
        voice_name = voice.get("name", voice_id)
        output_path = provider_dir / f"{voice_id}.m4a"
        text = f"Hi this is {voice_name} from Chatterbox"
        provider.save_to_file(text, output_path, voice=voice_id)

        assert output_path.exists(), f"Expected file {output_path} to be created"
        assert output_path.stat().st_size > 1000, "File should be non-empty"


def test_openai_provider(artifacts_dir):
    """Test OpenAI provider with 2 voices."""
    try:
        config = TTSConfig(cache_enabled=False)
        provider = OpenAIProvider(config)
    except (ImportError, ValueError) as e:
        pytest.skip(f"OpenAI provider not available: {e}")

    voices = provider.list_voices()[:2]

    provider_dir = artifacts_dir / "openai"
    provider_dir.mkdir(exist_ok=True)

    for voice in voices:
        voice_id = voice["id"]
        voice_name = voice.get("name", voice_id)
        output_path = provider_dir / f"{voice_id}.mp3"
        text = f"Hi this is {voice_name} from OpenAI"
        provider.save_to_file(text, output_path, voice=voice_id, format=AudioFormat.MP3)

        assert output_path.exists(), f"Expected file {output_path} to be created"
        assert output_path.stat().st_size > 1000, "File should be non-empty"


def test_elevenlabs_provider(artifacts_dir):
    """Test ElevenLabs provider with 2 voices."""
    try:
        config = TTSConfig(cache_enabled=False)
        provider = ElevenLabsProvider(config)
    except (ImportError, ValueError) as e:
        pytest.skip(f"ElevenLabs provider not available: {e}")

    voices = provider.list_voices()[:2]

    provider_dir = artifacts_dir / "elevenlabs"
    provider_dir.mkdir(exist_ok=True)

    for voice in voices:
        voice_id = voice["id"]
        voice_name = voice.get("name", voice_id)
        output_path = provider_dir / f"{voice_id}.mp3"
        text = f"Hi this is {voice_name} from ElevenLabs"
        provider.save_to_file(text, output_path, voice=voice_id, format=AudioFormat.MP3)

        assert output_path.exists(), f"Expected file {output_path} to be created"
        assert output_path.stat().st_size > 1000, "File should be non-empty"


def test_amazon_polly_provider(artifacts_dir):
    """Test Amazon Polly provider with 2 voices."""
    try:
        config = TTSConfig(cache_enabled=False)
        provider = AmazonPollyProvider(config)
    except (ImportError, ValueError) as e:
        pytest.skip(f"Amazon Polly provider not available: {e}")

    try:
        # Get 2 English voices
        voices = [v for v in provider.list_voices() if v.get("language", "").startswith("en-")][:2]
        assert len(voices) >= 2, "Need at least 2 English voices"
    except RuntimeError as e:
        pytest.skip(f"Failed to list voices (likely missing credentials): {e}")

    provider_dir = artifacts_dir / "polly"
    provider_dir.mkdir(exist_ok=True)

    for voice in voices:
        voice_id = voice["id"]
        voice_name = voice.get("name", voice_id)
        output_path = provider_dir / f"{voice_id}.mp3"
        text = f"Hi this is {voice_name} from Amazon Polly"
        provider.save_to_file(text, output_path, voice=voice_id, format=AudioFormat.MP3)

        assert output_path.exists(), f"Expected file {output_path} to be created"
        assert output_path.stat().st_size > 1000, "File should be non-empty"
