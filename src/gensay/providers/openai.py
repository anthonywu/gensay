"""OpenAI TTS provider implementation."""

from pathlib import Path
from typing import Any

from .base import AudioFormat, TTSConfig, TTSProvider


class OpenAIProvider(TTSProvider):
    """TTS provider using OpenAI's TTS API."""

    def __init__(self, config: TTSConfig | None = None):
        super().__init__(config)
        # TODO: Initialize OpenAI client with API key from config
        raise NotImplementedError("OpenAI TTS provider not yet implemented")

    def speak(self, text: str, voice: str | None = None, rate: int | None = None) -> None:
        """Speak text using OpenAI TTS."""
        raise NotImplementedError("OpenAI TTS speak not yet implemented")

    def save_to_file(
        self,
        text: str,
        output_path: str | Path,
        voice: str | None = None,
        rate: int | None = None,
        format: AudioFormat | None = None,
    ) -> Path:
        """Save speech to file using OpenAI TTS."""
        raise NotImplementedError("OpenAI TTS save_to_file not yet implemented")

    def list_voices(self) -> list[dict[str, Any]]:
        """List available OpenAI voices.

        OpenAI currently offers: alloy, echo, fable, onyx, nova, shimmer
        """
        raise NotImplementedError("OpenAI TTS list_voices not yet implemented")

    def get_supported_formats(self) -> list[AudioFormat]:
        """Get supported audio formats.

        OpenAI supports: mp3, opus, aac, flac
        """
        raise NotImplementedError("OpenAI TTS get_supported_formats not yet implemented")
