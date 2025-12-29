"""Tests for ElevenLabs provider."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gensay.providers import AudioFormat, ElevenLabsProvider, TTSConfig

# Directory for test artifacts (git-ignored)
ARTIFACTS_DIR = Path(__file__).parent / "artifacts"


def _elevenlabs_available() -> bool:
    """Check if elevenlabs library is available."""
    try:
        from elevenlabs import ElevenLabs  # noqa: F401

        return True
    except ImportError:
        return False


@pytest.fixture(scope="module", autouse=True)
def setup_artifacts_dir():
    """Create artifacts directory if it doesn't exist."""
    ARTIFACTS_DIR.mkdir(exist_ok=True)


@pytest.mark.skipif(
    not _elevenlabs_available() or not os.getenv("ELEVENLABS_API_KEY"),
    reason="ElevenLabs library not installed or API key not set",
)
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

        output_path = ARTIFACTS_DIR / "elevenlabs_test_alice_voice.mp3"
        result = provider.save_to_file("This is the Alice voice.", output_path, voice="Alice")

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
        with pytest.raises(ImportError, match="Install with:"):
            ElevenLabsProvider(config)

    @patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test-key"})
    def test_voice_settings_rate_mapping(self):
        """Test rate mapping to voice settings."""

        # Create a mock VoiceSettings class that stores kwargs as attributes
        class MockVoiceSettings:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        mock_client = MagicMock()

        import gensay.providers.elevenlabs as elevenlabs_module

        with (
            patch.object(elevenlabs_module, "ELEVENLABS_AVAILABLE", True),
            patch.object(elevenlabs_module, "ElevenLabs", mock_client, create=True),
            patch.object(elevenlabs_module, "VoiceSettings", MockVoiceSettings, create=True),
        ):
            config = TTSConfig()
            provider = ElevenLabsProvider(config)

            # Test different rates
            settings_slow = provider._get_voice_settings(100)
            settings_normal = provider._get_voice_settings(150)
            settings_fast = provider._get_voice_settings(200)

            # ElevenLabs v2 uses speed parameter (slower rate = lower speed)
            assert settings_slow.speed is not None
            assert settings_normal.speed is not None
            assert settings_fast.speed is not None
            assert settings_slow.speed < settings_normal.speed
            assert settings_normal.speed < settings_fast.speed
            # Check specific values: 100/150 = 0.67, 150/150 = 1.0, 200/150 = 1.33
            assert abs(settings_normal.speed - 1.0) < 0.01
