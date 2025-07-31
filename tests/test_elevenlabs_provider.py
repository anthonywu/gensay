"""Tests for ElevenLabs provider."""

import os
from unittest.mock import patch

import pytest

from gensay.providers import AudioFormat, ElevenLabsProvider, TTSConfig


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

    @patch("elevenlabs.play")
    @patch("elevenlabs.client.ElevenLabs.generate")
    def test_speak(self, mock_generate, mock_play):
        """Test speak functionality."""
        mock_generate.return_value = b"fake audio data"

        config = TTSConfig()
        provider = ElevenLabsProvider(config)

        provider.speak("Test speech")

        mock_generate.assert_called_once()
        mock_play.assert_called_once()

    @patch("elevenlabs.save")
    @patch("elevenlabs.client.ElevenLabs.generate")
    def test_save_to_file(self, mock_generate, mock_save):
        """Test save to file functionality."""
        mock_generate.return_value = b"fake audio data"

        config = TTSConfig()
        provider = ElevenLabsProvider(config)

        output_path = provider.save_to_file("Test speech", "output.mp3")

        assert output_path.name == "output.mp3"
        mock_generate.assert_called_once()
        mock_save.assert_called_once()


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
        assert settings_slow.stability > settings_normal.stability
        assert settings_normal.stability > settings_fast.stability
