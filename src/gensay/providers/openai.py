"""OpenAI TTS provider implementation."""

from collections.abc import Iterator
from typing import Any

try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from .base import AudioFormat, TTSConfig
from .cloud import CloudTTSProvider, PreparedSynthesis


class OpenAIProvider(CloudTTSProvider):
    """TTS provider using OpenAI's TTS API."""

    cache_namespace = "openai"
    display_name = "OpenAI"

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

    # OpenAI TTS models (as offered in the platform UI; passed through as-is,
    # so newer/dated snapshots not listed here still work via openai.model)
    MODELS = [
        {"id": "gpt-4o-mini-tts", "description": "Newest; steerable with instructions"},
        {"id": "gpt-4o-mini-tts-2025-03-20", "description": "Dated snapshot"},
        {"id": "gpt-4o-mini-tts-2025-12-15", "description": "Dated snapshot"},
        {"id": "tts-1", "description": "Fast, low latency (default)"},
        {"id": "tts-1-1106", "description": "Dated snapshot"},
        {"id": "tts-1-hd", "description": "Higher quality"},
        {"id": "tts-1-hd-1106", "description": "Dated snapshot"},
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

        api_key = self.resolve_api_key("OPENAI_API_KEY", config, display_name="OpenAI")
        self.client = OpenAI(api_key=api_key)
        # Default model - tts-1 is faster, tts-1-hd is higher quality
        self.model = (config.extra.get("model") if config else None) or "tts-1"

    def _prepare(
        self,
        text: str,
        voice: str | None,
        rate: int | None,
        format: AudioFormat | None,
    ) -> PreparedSynthesis:
        voice = voice or self.config.voice or "alloy"
        speed = self._rate_to_speed(rate)
        openai_format = "mp3" if format is None else self.FORMAT_MAP.get(format, "mp3")

        def _request():
            return self.client.audio.speech.with_streaming_response.create(
                model=self.model,
                voice=voice,
                input=text,
                speed=speed,
                response_format=openai_format,
            )

        def synthesize() -> bytes:
            with _request() as response:
                return response.read()

        def synthesize_stream() -> Iterator[bytes]:
            with _request() as response:
                yield from response.iter_bytes()

        return PreparedSynthesis(
            cache_parts=(text, voice, speed, self.model, openai_format),
            synthesize=synthesize,
            synthesize_stream=synthesize_stream,
        )

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

    def list_models(self) -> list[dict[str, Any]]:
        """List known OpenAI TTS models, marking the one this instance uses."""
        return [{**m, "current": m["id"] == self.model} for m in self.MODELS]

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
