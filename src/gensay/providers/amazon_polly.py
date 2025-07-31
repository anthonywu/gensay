"""Amazon Polly TTS provider implementation."""

from pathlib import Path
from typing import Any

from .base import AudioFormat, TTSConfig, TTSProvider


class AmazonPollyProvider(TTSProvider):
    """TTS provider using Amazon Polly service."""

    def __init__(self, config: TTSConfig | None = None):
        super().__init__(config)
        # TODO: Initialize AWS client with credentials from config
        raise NotImplementedError("Amazon Polly TTS provider not yet implemented")

    def speak(self, text: str, voice: str | None = None, rate: int | None = None) -> None:
        """Speak text using Amazon Polly."""
        raise NotImplementedError("Amazon Polly TTS speak not yet implemented")

    def save_to_file(
        self,
        text: str,
        output_path: str | Path,
        voice: str | None = None,
        rate: int | None = None,
        format: AudioFormat | None = None,
    ) -> Path:
        """Save speech to file using Amazon Polly."""
        raise NotImplementedError("Amazon Polly TTS save_to_file not yet implemented")

    def list_voices(self) -> list[dict[str, Any]]:
        """List available Amazon Polly voices.

        Polly offers many voices in various languages and accents.
        """
        raise NotImplementedError("Amazon Polly TTS list_voices not yet implemented")

    def get_supported_formats(self) -> list[AudioFormat]:
        """Get supported audio formats.

        Amazon Polly supports: mp3, ogg_vorbis, pcm
        """
        raise NotImplementedError("Amazon Polly TTS get_supported_formats not yet implemented")
