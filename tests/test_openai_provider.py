"""Tests for OpenAI TTS provider."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from gensay.providers import AudioFormat, OpenAIProvider, TTSConfig

# Directory for test artifacts (git-ignored)
ARTIFACTS_DIR = Path(__file__).parent / "artifacts"


@pytest.fixture(scope="module", autouse=True)
def setup_artifacts_dir():
    """Create artifacts directory if it doesn't exist."""
    ARTIFACTS_DIR.mkdir(exist_ok=True)


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not set")
class TestOpenAIProvider:
    """Test OpenAI provider functionality with real API."""

    def test_provider_initialization(self):
        """Test provider initializes with API key."""
        config = TTSConfig()
        provider = OpenAIProvider(config)
        assert provider.client is not None

    def test_list_voices(self):
        """Test listing available voices."""
        config = TTSConfig()
        provider = OpenAIProvider(config)

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
        provider = OpenAIProvider(config)

        formats = provider.get_supported_formats()
        assert AudioFormat.MP3 in formats
        assert AudioFormat.WAV in formats
        assert AudioFormat.OGG in formats

    def test_save_to_file_mp3(self):
        """Test saving speech to MP3 file."""
        config = TTSConfig()
        provider = OpenAIProvider(config)

        output_path = ARTIFACTS_DIR / "openai_test_output.mp3"
        result = provider.save_to_file("Hello from OpenAI TTS.", output_path)

        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_save_to_file_wav(self):
        """Test saving speech to WAV file."""
        config = TTSConfig()
        provider = OpenAIProvider(config)

        output_path = ARTIFACTS_DIR / "openai_test_output.wav"
        result = provider.save_to_file(
            "Testing WAV format output.", output_path, format=AudioFormat.WAV
        )

        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_save_with_different_voice(self):
        """Test saving with a specific voice."""
        config = TTSConfig()
        provider = OpenAIProvider(config)

        output_path = ARTIFACTS_DIR / "openai_test_nova_voice.mp3"
        result = provider.save_to_file("This is the Nova voice.", output_path, voice="nova")

        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_save_with_rate_adjustment(self):
        """Test saving with rate adjustment."""
        config = TTSConfig()
        provider = OpenAIProvider(config)

        output_path = ARTIFACTS_DIR / "openai_test_fast_rate.mp3"
        result = provider.save_to_file("This is spoken at a faster rate.", output_path, rate=200)

        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0


class TestOpenAIProviderMocked:
    """Test OpenAI provider with mocked dependencies."""

    @patch("gensay.providers.openai.OPENAI_AVAILABLE", False)
    def test_provider_without_library(self):
        """Test provider fails when library not installed."""
        config = TTSConfig()
        with pytest.raises(ImportError, match="Please install it with"):
            OpenAIProvider(config)

    def test_provider_without_api_key(self):
        """Test provider fails without API key."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            # Also clear any existing key
            env_backup = os.environ.pop("OPENAI_API_KEY", None)
            try:
                config = TTSConfig()
                with pytest.raises(ValueError, match="API key not found"):
                    OpenAIProvider(config)
            finally:
                if env_backup:
                    os.environ["OPENAI_API_KEY"] = env_backup

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("openai.OpenAI")
    def test_rate_to_speed_mapping(self, mock_client):
        """Test WPM rate to speed multiplier conversion."""
        config = TTSConfig()
        provider = OpenAIProvider(config)

        # Normal rate (150 WPM) = 1.0 speed
        assert provider._rate_to_speed(150) == 1.0

        # Slow rate (75 WPM) = 0.5 speed
        assert provider._rate_to_speed(75) == 0.5

        # Fast rate (300 WPM) = 2.0 speed
        assert provider._rate_to_speed(300) == 2.0

        # Very slow should clamp to 0.25
        assert provider._rate_to_speed(30) == 0.25

        # Very fast should clamp to 4.0
        assert provider._rate_to_speed(700) == 4.0

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("openai.OpenAI")
    def test_model_selection(self, mock_client):
        """Test model selection from config."""
        # Default model
        config = TTSConfig()
        provider = OpenAIProvider(config)
        assert provider.model == "tts-1"

        # HD model from config
        config_hd = TTSConfig(extra={"model": "tts-1-hd"})
        provider_hd = OpenAIProvider(config_hd)
        assert provider_hd.model == "tts-1-hd"
