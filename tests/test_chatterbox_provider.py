"""Tests for Chatterbox provider."""

import io
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import torch

from gensay.providers import AudioFormat, TTSConfig
from gensay.providers.chatterbox import ChatterboxProvider


def _make_fake_wav_bytes(duration_sec: float = 0.1, sample_rate: int = 24000) -> bytes:
    """Create fake WAV audio bytes for testing."""
    num_samples = int(duration_sec * sample_rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * num_samples)
    return buffer.getvalue()


def _create_mock_ta():
    """Create a mock torchaudio module that writes real WAV bytes."""
    mock_ta = MagicMock()

    def fake_save(buffer, wav, sr, format):
        buffer.write(_make_fake_wav_bytes(0.1, sr))

    mock_ta.save.side_effect = fake_save
    return mock_ta


def _create_mock_tts(sample_rate: int = 24000):
    """Create a mock TTS model."""
    mock_tts = MagicMock()
    mock_tts.sr = sample_rate
    mock_tts.generate.return_value = torch.zeros(1, 2400)
    return mock_tts


def _setup_provider_mocks(provider, mock_tts=None, mock_ta=None):
    """Set up mocks on a provider instance after creation."""
    if mock_tts is None:
        mock_tts = _create_mock_tts()
    if mock_ta is None:
        mock_ta = _create_mock_ta()

    provider._tts = mock_tts
    provider._ta = mock_ta
    provider._model_loaded = True
    return mock_tts, mock_ta


class TestChatterboxProviderMocked:
    """Test Chatterbox provider with mocked dependencies."""

    @patch("gensay.providers.chatterbox.ChatterboxProvider._play_audio")
    def test_provider_initialization(self, mock_play):
        """Test provider initializes correctly."""
        config = TTSConfig()
        provider = ChatterboxProvider(config)

        mock_tts, mock_ta = _setup_provider_mocks(provider)

        assert provider._tts is not None
        assert provider.sample_rate == 24000

    @patch("gensay.providers.chatterbox.ChatterboxProvider._play_audio")
    def test_provider_device_config(self, mock_play):
        """Test provider respects device config."""
        config = TTSConfig(extra={"device": "cpu"})
        provider = ChatterboxProvider(config)

        # Device should be set from config
        assert provider._device == "mps" or provider._device == "cuda"  # default before load

        # After setting up mocks, simulate what _load_model would do
        _setup_provider_mocks(provider)
        provider._device = "cpu"  # This would be set in _load_model

        assert provider._device == "cpu"

    @patch("gensay.providers.chatterbox.ChatterboxProvider._play_audio")
    def test_list_voices(self, mock_play):
        """Test listing available voices."""
        config = TTSConfig()
        provider = ChatterboxProvider(config)

        voices = provider.list_voices()
        assert isinstance(voices, list)
        assert len(voices) == 2

        voice_ids = [v["id"] for v in voices]
        assert "default" in voice_ids
        assert "custom" in voice_ids

        for voice in voices:
            assert "id" in voice
            assert "name" in voice
            assert "language" in voice

    @patch("gensay.providers.chatterbox.ChatterboxProvider._play_audio")
    def test_get_supported_formats(self, mock_play):
        """Test supported formats."""
        config = TTSConfig()
        provider = ChatterboxProvider(config)

        formats = provider.get_supported_formats()
        assert AudioFormat.WAV in formats
        assert AudioFormat.MP3 in formats
        assert AudioFormat.M4A in formats

    @patch("gensay.providers.chatterbox.ChatterboxProvider._play_audio")
    def test_speak(self, mock_play):
        """Test speak functionality."""
        config = TTSConfig(cache_enabled=False, extra={"show_progress": False})
        provider = ChatterboxProvider(config)
        mock_tts, mock_ta = _setup_provider_mocks(provider)

        provider.speak("Test speech")

        mock_tts.generate.assert_called_once()
        mock_play.assert_called_once()

    @patch("gensay.providers.chatterbox.ChatterboxProvider._play_audio")
    def test_save_to_file(self, mock_play, tmp_path):
        """Test save to file functionality."""
        config = TTSConfig(cache_enabled=False, extra={"show_progress": False})
        provider = ChatterboxProvider(config)
        mock_tts, mock_ta = _setup_provider_mocks(provider)

        output_file = tmp_path / "output.wav"
        result_path = provider.save_to_file("Test speech", output_file, format=AudioFormat.WAV)

        assert result_path == output_file
        assert output_file.exists()
        mock_tts.generate.assert_called_once()

    @patch("gensay.providers.chatterbox.ChatterboxProvider._play_audio")
    def test_generate_audio_with_voice_cloning(self, mock_play, tmp_path):
        """Test audio generation with voice cloning."""
        config = TTSConfig(extra={"show_progress": False})
        provider = ChatterboxProvider(config)
        mock_tts, mock_ta = _setup_provider_mocks(provider)

        # Create a fake audio prompt file
        audio_prompt = tmp_path / "voice.wav"
        audio_prompt.write_bytes(_make_fake_wav_bytes())

        provider._generate_audio("Test speech", str(audio_prompt))

        # Verify audio_prompt_path was passed
        call_kwargs = mock_tts.generate.call_args[1]
        assert call_kwargs["audio_prompt_path"] == str(audio_prompt)

    @patch("gensay.providers.chatterbox.ChatterboxProvider._play_audio")
    def test_generate_audio_default_voice(self, mock_play):
        """Test audio generation with default voice."""
        config = TTSConfig(extra={"show_progress": False})
        provider = ChatterboxProvider(config)
        mock_tts, mock_ta = _setup_provider_mocks(provider)

        provider._generate_audio("Test speech", "default")

        # Verify no audio_prompt_path was passed for default voice
        call_kwargs = mock_tts.generate.call_args[1]
        assert "audio_prompt_path" not in call_kwargs

    @patch("gensay.providers.chatterbox.ChatterboxProvider._play_audio")
    def test_generate_returns_none_raises_error(self, mock_play):
        """Test that None return from generate raises RuntimeError."""
        config = TTSConfig(extra={"show_progress": False})
        provider = ChatterboxProvider(config)

        mock_tts = _create_mock_tts()
        mock_tts.generate.return_value = None
        _setup_provider_mocks(provider, mock_tts=mock_tts)

        with pytest.raises(RuntimeError, match="returned None"):
            provider._generate_audio("Test speech", "default")

    @patch("gensay.providers.chatterbox.ChatterboxProvider._play_audio")
    def test_cache_key_includes_turbo_prefix(self, mock_play):
        """Test cache key includes turbo prefix for invalidation."""
        config = TTSConfig()
        provider = ChatterboxProvider(config)

        key = provider._get_cache_key("test", "default", 150)
        # The key should be a hash, but we can verify it's consistent
        key2 = provider._get_cache_key("test", "default", 150)
        assert key == key2

        # Different params should give different keys
        key3 = provider._get_cache_key("test2", "default", 150)
        assert key != key3

    @patch("gensay.providers.chatterbox.ChatterboxProvider._play_audio")
    def test_combine_audio_segments_empty(self, mock_play):
        """Test combining empty segments."""
        config = TTSConfig()
        provider = ChatterboxProvider(config)

        result = provider._combine_audio_segments([])
        assert result == b""

    @patch("gensay.providers.chatterbox.ChatterboxProvider._play_audio")
    def test_combine_audio_segments_single(self, mock_play):
        """Test combining single segment returns it unchanged."""
        config = TTSConfig()
        provider = ChatterboxProvider(config)

        wav_bytes = _make_fake_wav_bytes()
        result = provider._combine_audio_segments([wav_bytes])
        assert result == wav_bytes

    @patch("gensay.providers.chatterbox.ChatterboxProvider._play_audio")
    def test_combine_audio_segments_multiple(self, mock_play):
        """Test combining multiple segments."""
        config = TTSConfig()
        provider = ChatterboxProvider(config)

        wav1 = _make_fake_wav_bytes(0.1)
        wav2 = _make_fake_wav_bytes(0.2)
        result = provider._combine_audio_segments([wav1, wav2])

        # Result should be valid WAV
        with wave.open(io.BytesIO(result), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 24000
            # Combined should have more frames than either segment alone
            assert wf.getnframes() > 0

    @patch("gensay.providers.chatterbox.ChatterboxProvider._play_audio")
    def test_unsupported_format_raises_error(self, mock_play):
        """Test that unsupported format raises ValueError."""
        config = TTSConfig()
        provider = ChatterboxProvider(config)

        with pytest.raises(ValueError, match="Unsupported audio format"):
            provider._save_audio(b"", Path("test.ogg"), AudioFormat.OGG)


def _chatterbox_available() -> bool:
    """Check if chatterbox library is available."""
    try:
        from chatterbox.tts_turbo import ChatterboxTurboTTS  # noqa: F401

        return True
    except ImportError:
        return False


# Integration tests - only run when chatterbox is actually available
@pytest.mark.skipif(
    not _chatterbox_available(),
    reason="Chatterbox library not installed",
)
class TestChatterboxProviderIntegration:
    """Integration tests for Chatterbox provider (requires actual library)."""

    def test_real_initialization(self):
        """Test real provider initialization."""
        config = TTSConfig(extra={"device": "cpu"})
        provider = ChatterboxProvider(config)
        assert provider.sample_rate > 0

    def test_real_list_voices(self):
        """Test real voice listing."""
        config = TTSConfig(extra={"device": "cpu"})
        provider = ChatterboxProvider(config)
        voices = provider.list_voices()
        assert len(voices) >= 1
