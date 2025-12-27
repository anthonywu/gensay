"""Tests for ElevenLabs provider."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from gensay.providers import AudioFormat, ElevenLabsProvider, TTSConfig

# Directory for test artifacts (git-ignored)
ARTIFACTS_DIR = Path(__file__).parent / "artifacts"


@pytest.fixture(scope="module", autouse=True)
def setup_artifacts_dir():
    """Create artifacts directory if it doesn't exist."""
    ARTIFACTS_DIR.mkdir(exist_ok=True)


@pytest.mark.skipif(not os.getenv("ELEVENLABS_API_KEY"), reason="ElevenLabs API key not set")
class TestElevenLabsProvider:
    """Test ElevenLabs provider functionality."""

    def test_provider_initialization(self):
        """Test provider initializes with API key."""
        config = TTSConfig()
        provider = ElevenLabsProvider(config)
        assert provider.client is not None

    def test_provider_without_api_key(self):
        """Test provider fails without API key."""
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": ""}):
            config = TTSConfig()
            with pytest.raises(ValueError, match="API key not found"):
                ElevenLabsProvider(config)

    def test_list_voices(self):
        """Test listing available voices."""
        config = TTSConfig()
        provider = ElevenLabsProvider(config)

        voices = provider.list_voices()
        assert isinstance(voices, list)
        assert len(voices) > 0

        # Check voice structure
        for voice in voices:
            assert "id" in voice
            assert "name" in voice
            assert "language" in voice

    def test_get_supported_formats(self):
        """Test supported formats."""
        config = TTSConfig()
        provider = ElevenLabsProvider(config)

        formats = provider.get_supported_formats()
        assert AudioFormat.MP3 in formats
        assert AudioFormat.WAV in formats

    def test_save_to_file_mp3(self):
        """Test saving speech to MP3 file."""
        config = TTSConfig()
        provider = ElevenLabsProvider(config)

        output_path = ARTIFACTS_DIR / "elevenlabs_test_output.mp3"
        result = provider.save_to_file("Hello from ElevenLabs TTS.", output_path)

        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_save_to_file_wav(self):
        """Test saving speech to WAV file."""
        config = TTSConfig()
        provider = ElevenLabsProvider(config)

        output_path = ARTIFACTS_DIR / "elevenlabs_test_output.wav"
        result = provider.save_to_file(
            "Testing WAV format output.", output_path, format=AudioFormat.WAV
        )

        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_save_with_different_voice(self):
        """Test saving with a specific voice."""
        config = TTSConfig()
        provider = ElevenLabsProvider(config)

        output_path = ARTIFACTS_DIR / "elevenlabs_test_aria_voice.mp3"
        result = provider.save_to_file("This is the Aria voice.", output_path, voice="Aria")

        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_save_with_rate_adjustment(self):
        """Test saving with rate adjustment."""
        config = TTSConfig()
        provider = ElevenLabsProvider(config)

        output_path = ARTIFACTS_DIR / "elevenlabs_test_fast_rate.mp3"
        result = provider.save_to_file("This is spoken at a faster rate.", output_path, rate=200)

        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0


class TestElevenLabsProviderMocked:
    """Test ElevenLabs provider with mocked dependencies."""

    @patch("gensay.providers.elevenlabs.ELEVENLABS_AVAILABLE", False)
    def test_provider_without_library(self):
        """Test provider fails when library not installed."""
        config = TTSConfig()
        with pytest.raises(ImportError, match="Please install it with"):
            ElevenLabsProvider(config)

    @patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test-key"})
    @patch("elevenlabs.client.ElevenLabs")
    def test_voice_settings_rate_mapping(self, mock_client):
        """Test rate mapping to voice settings."""
        config = TTSConfig()
        provider = ElevenLabsProvider(config)

        # Test different rates
        settings_slow = provider._get_voice_settings(100)
        settings_normal = provider._get_voice_settings(150)
        settings_fast = provider._get_voice_settings(200)

        # Slower rate should have higher stability
        assert settings_slow.stability is not None
        assert settings_normal.stability is not None
        assert settings_fast.stability is not None
        assert settings_slow.stability > settings_normal.stability
        assert settings_normal.stability > settings_fast.stability
