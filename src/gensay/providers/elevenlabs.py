"""ElevenLabs TTS provider implementation."""

import io
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elevenlabs import VoiceSettings

try:
    from elevenlabs import ElevenLabs, VoiceSettings
    from elevenlabs.play import play

    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False

from .base import AudioFormat, TTSConfig
from .cloud import CloudTTSProvider, PreparedSynthesis

# eleven_monolingual_v1 / eleven_multilingual_v1 were retired by ElevenLabs.
# Flash is the right default for a notification tool (lowest latency).
# Override per-user: gensay config set elevenlabs.model eleven_v3
DEFAULT_MODEL = "eleven_flash_v2_5"


class ElevenLabsProvider(CloudTTSProvider):
    """TTS provider using ElevenLabs API."""

    cache_namespace = "elevenlabs"
    display_name = "ElevenLabs"

    # ElevenLabs TTS models (also queryable live via GET /v1/models; hardcoded
    # so listing works offline — unlisted ids still pass through as-is)
    MODELS = [
        {"id": "eleven_v3", "description": "Newest, most expressive; 70+ languages; audio tags"},
        {"id": "eleven_multilingual_v2", "description": "Highest quality, long-form; 29 languages"},
        {"id": "eleven_flash_v2_5", "description": "Ultra-low latency, cheapest (default)"},
        {"id": "eleven_flash_v2", "description": "Ultra-low latency, English only"},
        {"id": "eleven_turbo_v2_5", "description": "Deprecated — use eleven_flash_v2_5"},
        {"id": "eleven_turbo_v2", "description": "Deprecated — use eleven_flash_v2"},
    ]

    # Map our formats to ElevenLabs supported formats
    FORMAT_MAP = {
        AudioFormat.MP3: "mp3_44100_128",
        AudioFormat.OGG: "mp3_44100_128",  # ElevenLabs doesn't support OGG, use MP3
        AudioFormat.WAV: "pcm_24000",  # PCM is raw WAV data
        AudioFormat.FLAC: "mp3_44100_128",  # Use MP3 as fallback
        AudioFormat.AAC: "mp3_44100_128",  # Use MP3 as fallback
        AudioFormat.M4A: "mp3_44100_128",  # Use MP3 as fallback
    }

    def __init__(self, config: TTSConfig | None = None):
        super().__init__(config)

        if not ELEVENLABS_AVAILABLE:
            raise ImportError(
                "ElevenLabs provider requires additional dependencies. "
                "Install with: [uv tool | pip ] install 'gensay[elevenlabs]'"
            )

        api_key = self.resolve_api_key("ELEVENLABS_API_KEY", config, display_name="ElevenLabs")
        self.client = ElevenLabs(api_key=api_key)
        self.model = (config.extra.get("model") if config else None) or DEFAULT_MODEL
        self._voice_cache: list[dict[str, Any]] | None = None
        self._voice_id_map: dict[str, str] | None = None  # name -> voice_id

    def _prepare(
        self,
        text: str,
        voice: str | None,
        rate: int | None,
        format: AudioFormat | None,
    ) -> PreparedSynthesis:
        voice_name = voice or self.config.voice or "Sarah"
        voice_id = self._resolve_voice_id(voice_name)
        voice_settings = self._get_voice_settings(rate)
        model = self.model
        el_format = (
            "mp3_44100_128" if format is None else self.FORMAT_MAP.get(format, "mp3_44100_128")
        )

        def synthesize_stream() -> Iterator[bytes]:
            # text_to_speech.convert (v2 API) already yields audio chunks
            yield from self.client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                voice_settings=voice_settings,
                model_id=model,
                output_format=el_format,
            )

        def synthesize() -> bytes:
            return b"".join(synthesize_stream())

        # Explicit VoiceSettings fields (not the object's repr, which the SDK
        # may change between releases and would silently invalidate caches).
        settings = (
            f"{voice_settings.stability}|{voice_settings.similarity_boost}"
            f"|{voice_settings.style}|{voice_settings.use_speaker_boost}|{voice_settings.speed}"
        )
        return PreparedSynthesis(
            cache_parts=(text, voice_id, settings, el_format, model),
            synthesize=synthesize,
            synthesize_stream=synthesize_stream,
        )

    def _play(self, audio_data: bytes, suffix: str) -> None:  # noqa: ARG002
        """Play via the ElevenLabs SDK (pyaudio when available, else ffplay)."""
        play(io.BytesIO(audio_data))

    def list_models(self) -> list[dict[str, Any]]:
        """List known ElevenLabs TTS models, marking the one this instance uses."""
        return [{**m, "current": m["id"] == self.model} for m in self.MODELS]

    def list_voices(self) -> list[dict[str, Any]]:
        """List available ElevenLabs voices."""
        if self._voice_cache is None:
            try:
                # Get all available voices using the client
                response = self.client.voices.get_all()
                self._voice_cache = []
                self._voice_id_map = {}

                for voice in response.voices:
                    voice_data = {
                        "id": voice.voice_id,
                        "name": voice.name,
                        "language": "en-US",  # ElevenLabs voices are multilingual
                        "category": voice.category,
                    }

                    # Build name -> voice_id map (case-insensitive)
                    # Support both full name and short name (before " - ")
                    self._voice_id_map[voice.name.lower()] = voice.voice_id
                    if " - " in voice.name:
                        short_name = voice.name.split(" - ")[0].lower()
                        self._voice_id_map[short_name] = voice.voice_id

                    # Add labels if available
                    if voice.labels:
                        voice_data.update(
                            {
                                "gender": voice.labels.get("gender", "neutral"),
                                "description": voice.labels.get("description", ""),
                                "use_case": voice.labels.get("use case", ""),
                                "accent": voice.labels.get("accent", ""),
                                "age": voice.labels.get("age", ""),
                            }
                        )

                    self._voice_cache.append(voice_data)

            except Exception as e:
                raise RuntimeError(f"Failed to list voices: {e}") from e

        return self._voice_cache

    def _resolve_voice_id(self, voice: str) -> str:
        """Resolve a voice name or ID to a voice ID."""
        # Populate voice cache if needed
        if self._voice_id_map is None or self._voice_cache is None:
            self.list_voices()

        voice_id_map = self._voice_id_map
        voice_cache = self._voice_cache
        assert voice_id_map is not None, "Voice ID map should be populated"
        assert voice_cache is not None, "Voice cache should be populated"

        # Check if it's already a known voice ID
        known_ids = {v["id"] for v in voice_cache}
        if voice in known_ids:
            return voice

        # Look up by name (case-insensitive)
        if voice_id := voice_id_map.get(voice.lower()):
            return voice_id

        raise ValueError(
            f"Voice '{voice}' not found. See available voices with `gensay -p elevenlabs -v '?'`."
        )

    def get_supported_formats(self) -> list[AudioFormat]:
        """Get supported audio formats."""
        # ElevenLabs primarily supports MP3 and PCM
        return [
            AudioFormat.MP3,
            AudioFormat.WAV,  # via PCM
            # Other formats will use MP3 as fallback
            AudioFormat.M4A,
            AudioFormat.AAC,
            AudioFormat.OGG,
            AudioFormat.FLAC,
        ]

    def _get_voice_settings(self, rate: int | None = None) -> "VoiceSettings":
        """Get voice settings with optional rate adjustment."""
        # ElevenLabs v2 supports speed parameter (0.7-1.2, 1.0 is normal)
        # Map WPM rate to speed multiplier:
        # Normal rate ~150 WPM = 1.0 speed
        # Fast rate ~180 WPM = 1.2 speed (max)
        # Slow rate ~105 WPM = 0.7 speed (min)
        speed = (rate / 150.0) if rate else 1.0
        speed = max(0.7, min(1.2, speed))  # Clamp to API-allowed range

        return VoiceSettings(
            stability=0.5,
            similarity_boost=0.75,
            style=0.0,
            use_speaker_boost=True,
            speed=speed,
        )
