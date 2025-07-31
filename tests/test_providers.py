"""Tests for TTS providers."""

import sys
import tempfile
from pathlib import Path

import pytest

from gensay.providers import AudioFormat, MacOSSayProvider, MockProvider, TTSConfig


def test_mock_provider_speak():
    """Test MockProvider speak functionality."""
    config = TTSConfig(voice="test-voice", rate=200)
    provider = MockProvider(config)

    provider.speak("Hello, world!")
    assert provider.last_spoken_text == "Hello, world!"


def test_mock_provider_save_to_file():
    """Test MockProvider save_to_file functionality."""
    config = TTSConfig()
    provider = MockProvider(config)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test.m4a"
        result = provider.save_to_file("Test audio", output_path)

        assert result == output_path
        assert output_path.exists()
        assert provider.last_saved_file == output_path


def test_mock_provider_list_voices():
    """Test MockProvider voice listing."""
    provider = MockProvider()
    voices = provider.list_voices()

    assert len(voices) > 0
    assert all("id" in v and "name" in v for v in voices)


def test_audio_format_from_extension():
    """Test AudioFormat.from_extension."""
    assert AudioFormat.from_extension("test.m4a") == AudioFormat.M4A
    assert AudioFormat.from_extension("audio.wav") == AudioFormat.WAV
    assert AudioFormat.from_extension(Path("file.mp3")) == AudioFormat.MP3

    with pytest.raises(ValueError):
        AudioFormat.from_extension("file.xyz")


def test_progress_callback():
    """Test progress callback functionality."""
    progress_updates = []

    def callback(progress: float, message: str):
        progress_updates.append((progress, message))

    config = TTSConfig(progress_callback=callback)
    provider = MockProvider(config)

    provider.speak("Test with progress")

    assert len(progress_updates) > 0
    assert progress_updates[-1][0] == 1.0  # Final progress should be 100%


@pytest.mark.skipif(
    sys.platform != "darwin" or not Path("/usr/bin/say").exists(), reason="macOS say not available"
)
def test_macos_provider_list_voices():
    """Test macOS provider voice listing."""
    provider = MacOSSayProvider()
    voices = provider.list_voices()

    assert len(voices) > 0
    # Check that we have some standard fields
    assert all("id" in v and "language" in v for v in voices)
    # Check that we have at least some English voices
    assert any("en" in v.get("language", "") for v in voices)
