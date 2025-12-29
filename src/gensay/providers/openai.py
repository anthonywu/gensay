"""OpenAI TTS provider implementation."""

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from ..cache import TTSCache
from .base import AudioFormat, TTSConfig, TTSProvider


class OpenAIProvider(TTSProvider):
    """TTS provider using OpenAI's TTS API."""

    # OpenAI TTS voices
    VOICES = [
        {"id": "alloy", "name": "Alloy", "description": "Neutral, balanced"},
        {"id": "ash", "name": "Ash", "description": "Warm, conversational"},
        {"id": "coral", "name": "Coral", "description": "Clear, professional"},
        {"id": "echo", "name": "Echo", "description": "Soft, gentle"},
        {"id": "fable", "name": "Fable", "description": "Expressive, British accent"},
        {"id": "onyx", "name": "Onyx", "description": "Deep, authoritative"},
        {"id": "nova", "name": "Nova", "description": "Friendly, upbeat"},
        {"id": "sage", "name": "Sage", "description": "Wise, calm"},
        {"id": "shimmer", "name": "Shimmer", "description": "Warm, engaging"},
    ]

    # Map our formats to OpenAI supported formats
    FORMAT_MAP = {
        AudioFormat.MP3: "mp3",
        AudioFormat.OGG: "opus",  # OpenAI uses opus for ogg container
        AudioFormat.WAV: "wav",
        AudioFormat.FLAC: "flac",
        AudioFormat.AAC: "aac",
        AudioFormat.M4A: "aac",  # M4A uses AAC codec
    }

    def __init__(self, config: TTSConfig | None = None):
        super().__init__(config)

        if not OPENAI_AVAILABLE:
            raise ImportError(
                "OpenAI library not found. Please install it with: pip install openai"
            )

        # Get API key from environment or config
        api_key = os.getenv("OPENAI_API_KEY") or (config.extra.get("api_key") if config else None)

        if not api_key:
            raise ValueError(
                "OpenAI API key not found. Please set OPENAI_API_KEY "
                "environment variable or pass it in config.extra['api_key']"
            )

        self.client = OpenAI(api_key=api_key)
        # Default model - tts-1 is faster, tts-1-hd is higher quality
        self.model = (config.extra.get("model") if config else None) or "tts-1"
        self._cache = TTSCache(enabled=config.cache_enabled if config else True)

    def speak(self, text: str, voice: str | None = None, rate: int | None = None) -> None:
        """Speak text using OpenAI TTS."""
        voice = voice or self.config.voice or "alloy"
        speed = self._rate_to_speed(rate)
        cache_key = self._get_cache_key(text, voice, speed, "mp3")

        try:
            self.update_progress(0.0, "Checking cache...")

            audio_data = self._cache.get(cache_key)

            if audio_data is None:
                self.update_progress(0.2, "Generating speech...")

                # Generate audio to a temp file
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    temp_path = Path(f.name)

                with self.client.audio.speech.with_streaming_response.create(
                    model=self.model,
                    voice=voice,
                    input=text,
                    speed=speed,
                    response_format="mp3",
                ) as response:
                    response.stream_to_file(temp_path)

                audio_data = temp_path.read_bytes()
                self._cache.put(cache_key, audio_data)

                self.update_progress(0.5, "Playing audio...")
            else:
                self.update_progress(0.5, "Using cached audio...")

                # Write to temp file for playback
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    temp_path = Path(f.name)
                temp_path.write_bytes(audio_data)

            # Play using afplay on macOS
            subprocess.run(["afplay", str(temp_path)], check=True)

            self.update_progress(1.0, "Complete")

        except Exception as e:
            raise RuntimeError(f"OpenAI TTS failed: {e}") from e
        finally:
            # Clean up temp file
            if temp_path.exists():
                temp_path.unlink()

    def save_to_file(
        self,
        text: str,
        output_path: str | Path,
        voice: str | None = None,
        rate: int | None = None,
        format: AudioFormat | None = None,
    ) -> Path:
        """Save speech to file using OpenAI TTS."""
        output_path = Path(output_path)
        voice = voice or self.config.voice or "alloy"
        format = format or self.config.format or AudioFormat.from_extension(output_path)
        speed = self._rate_to_speed(rate)

        # Map format to OpenAI format
        openai_format = self.FORMAT_MAP.get(format, "mp3")
        cache_key = self._get_cache_key(text, voice, speed, openai_format)

        try:
            self.update_progress(0.0, "Checking cache...")

            audio_data = self._cache.get(cache_key)

            if audio_data is None:
                self.update_progress(0.2, "Generating speech...")

                with self.client.audio.speech.with_streaming_response.create(
                    model=self.model,
                    voice=voice,
                    input=text,
                    speed=speed,
                    response_format=openai_format,
                ) as response:
                    response.stream_to_file(output_path)

                self.update_progress(0.5, "Saving to file...")
                audio_data = output_path.read_bytes()
                self._cache.put(cache_key, audio_data)
            else:
                self.update_progress(0.5, "Using cached audio...")
                output_path.write_bytes(audio_data)

            self.update_progress(1.0, "Complete")

            return output_path

        except Exception as e:
            raise RuntimeError(f"OpenAI TTS failed: {e}") from e

    def list_voices(self) -> list[dict[str, Any]]:
        """List available OpenAI voices."""
        # OpenAI voices are static, return the known list
        return [
            {
                "id": v["id"],
                "name": v["name"],
                "language": "multilingual",
                "description": v["description"],
            }
            for v in self.VOICES
        ]

    def get_supported_formats(self) -> list[AudioFormat]:
        """Get supported audio formats.

        OpenAI supports: mp3, opus, aac, flac, wav, pcm
        """
        return [
            AudioFormat.MP3,
            AudioFormat.OGG,  # via opus
            AudioFormat.WAV,
            AudioFormat.FLAC,
            AudioFormat.AAC,
            AudioFormat.M4A,  # via aac
        ]

    def _rate_to_speed(self, rate: int | None) -> float:
        """Convert WPM rate to OpenAI speed multiplier.

        OpenAI speed: 0.25 to 4.0, where 1.0 is normal speed.
        Normal speaking rate is ~150 WPM.
        """
        if rate is None:
            rate = self.config.rate
        if rate is None:
            return 1.0

        # Map WPM to speed multiplier
        # 150 WPM = 1.0 speed
        # 75 WPM = 0.5 speed
        # 300 WPM = 2.0 speed
        speed = rate / 150.0
        # Clamp to OpenAI's supported range
        return max(0.25, min(4.0, speed))

    def _get_cache_key(self, text: str, voice: str, speed: float, format: str) -> str:
        """Generate cache key for text/voice/speed/format combination."""
        data = f"openai|{text}|{voice}|{speed}|{self.model}|{format}"
        return hashlib.sha256(data.encode()).hexdigest()
