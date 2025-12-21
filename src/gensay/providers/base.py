"""Base TTS provider interface and common types."""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class AudioFormat(Enum):
    """Supported audio output formats."""

    AIFF = "aiff"
    WAV = "wav"
    M4A = "m4a"
    MP3 = "mp3"
    CAF = "caf"
    FLAC = "flac"
    AAC = "aac"
    OGG = "ogg"

    @classmethod
    def from_extension(cls, path: str | Path) -> "AudioFormat":
        """Get format from file extension."""
        ext = Path(path).suffix.lower().lstrip(".")
        for format in cls:
            if format.value == ext:
                return format
        raise ValueError(f"Unsupported audio format: {ext}")


ProgressCallback = Callable[[float, str], None]
"""Progress callback signature: (progress: 0.0-1.0, status_message)"""


@dataclass
class TTSConfig:
    """Configuration for TTS providers."""

    voice: str | None = None
    rate: int | None = None  # Words per minute
    pitch: float | None = None  # Pitch adjustment
    volume: float | None = None  # Volume 0.0-1.0
    format: AudioFormat = AudioFormat.M4A
    quality: int | None = None  # 0-127 where 127 is highest
    cache_enabled: bool = True
    cache_dir: Path | None = None
    progress_callback: ProgressCallback | None = None
    # Provider-specific config
    extra: dict[str, Any] = field(default_factory=dict)


class TTSProvider(ABC):
    """Abstract base class for TTS providers."""

    config: TTSConfig

    def __init__(self, config: TTSConfig | None = None):
        self.config = config or TTSConfig()

    @abstractmethod
    def speak(self, text: str, voice: str | None = None, rate: int | None = None) -> None:
        """Speak text using the TTS engine."""
        pass

    @abstractmethod
    def save_to_file(
        self,
        text: str,
        output_path: str | Path,
        voice: str | None = None,
        rate: int | None = None,
        format: AudioFormat | None = None,
    ) -> Path:
        """Save speech to an audio file."""
        pass

    @abstractmethod
    def list_voices(self) -> list[dict[str, Any]]:
        """List available voices.

        Returns list of dicts with at least 'id' and 'name' keys.
        """
        pass

    @abstractmethod
    def get_supported_formats(self) -> list[AudioFormat]:
        """Get list of supported audio formats."""
        pass

    def is_format_supported(self, format: AudioFormat) -> bool:
        """Check if format is supported."""
        return format in self.get_supported_formats()

    async def speak_async(
        self, text: str, voice: str | None = None, rate: int | None = None
    ) -> None:
        """Async version of speak."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.speak, text, voice, rate)

    async def save_to_file_async(
        self,
        text: str,
        output_path: str | Path,
        voice: str | None = None,
        rate: int | None = None,
        format: AudioFormat | None = None,
    ) -> Path:
        """Async version of save_to_file."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.save_to_file, text, output_path, voice, rate, format
        )

    def update_progress(self, progress: float, message: str = "") -> None:
        """Update progress if callback is configured."""
        if self.config.progress_callback:
            self.config.progress_callback(progress, message)
