"""ElevenLabs TTS provider implementation."""

import hashlib
import io
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elevenlabs import VoiceSettings

try:
    from elevenlabs import ElevenLabs, VoiceSettings
    from elevenlabs.play import play

    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False

from ..cache import TTSCache
from .base import AudioFormat, TTSConfig, TTSProvider


class ElevenLabsProvider(TTSProvider):
    """TTS provider using ElevenLabs API."""

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

        # Get API key from environment or config
        api_key = os.getenv("ELEVENLABS_API_KEY") or (
            config.extra.get("api_key") if config else None
        )

        if not api_key:
            raise ValueError(
                "ElevenLabs API key not found. Please set ELEVENLABS_API_KEY "
                "environment variable or pass it in config.extra['api_key']"
            )

        self.client = ElevenLabs(api_key=api_key)
        self._voice_cache: list[dict[str, Any]] | None = None
        self._voice_id_map: dict[str, str] | None = None  # name -> voice_id
        self._cache = TTSCache(enabled=config.cache_enabled if config else True)

    def speak(self, text: str, voice: str | None = None, rate: int | None = None) -> None:
        """Speak text using ElevenLabs TTS."""
        voice_name = voice or self.config.voice or "Sarah"
        voice_id = self._resolve_voice_id(voice_name)

        # Get voice settings
        voice_settings = self._get_voice_settings(rate)
        cache_key = self._get_cache_key(text, voice_id, voice_settings, "mp3_44100_128")

        try:
            self.update_progress(0.0, "Checking cache...")

            audio_data = self._cache.get(cache_key)

            if audio_data is None:
                self.update_progress(0.2, "Generating speech...")

                # Generate audio using text_to_speech.convert (v2 API)
                audio = self.client.text_to_speech.convert(
                    voice_id=voice_id,
                    text=text,
                    voice_settings=voice_settings,
                    model_id="eleven_monolingual_v1",
                )

                # Convert to bytes for caching
                buffer = io.BytesIO()
                for chunk in audio:
                    buffer.write(chunk)
                audio_data = buffer.getvalue()

                self._cache.put(cache_key, audio_data)
            else:
                self.update_progress(0.5, "Using cached audio...")

            self.update_progress(0.8, "Playing audio...")

            # Convert bytes back to audio format
            audio = io.BytesIO(audio_data)
            play(audio)

            self.update_progress(1.0, "Complete")

        except Exception as e:
            raise RuntimeError(f"ElevenLabs TTS failed: {e}") from e

    def save_to_file(
        self,
        text: str,
        output_path: str | Path,
        voice: str | None = None,
        rate: int | None = None,
        format: AudioFormat | None = None,
    ) -> Path:
        """Save speech to file using ElevenLabs TTS."""
        output_path = Path(output_path)
        voice_name = voice or self.config.voice or "Sarah"
        voice_id = self._resolve_voice_id(voice_name)
        format = format or self.config.format or AudioFormat.from_extension(output_path)

        # Get voice settings
        voice_settings = self._get_voice_settings(rate)

        # Map format to ElevenLabs format
        el_format = self.FORMAT_MAP.get(format, "mp3_44100_128")
        cache_key = self._get_cache_key(text, voice_id, voice_settings, el_format)

        try:
            self.update_progress(0.0, "Checking cache...")

            audio_data = self._cache.get(cache_key)

            if audio_data is None:
                self.update_progress(0.2, "Generating speech...")

                # Generate audio using text_to_speech.convert (v2 API)
                audio = self.client.text_to_speech.convert(
                    voice_id=voice_id,
                    text=text,
                    voice_settings=voice_settings,
                    model_id="eleven_monolingual_v1",
                    output_format=el_format,
                )

                self.update_progress(0.5, "Saving to file...")

                # Convert to bytes for caching and saving
                buffer = io.BytesIO()
                for chunk in audio:
                    buffer.write(chunk)
                audio_data = buffer.getvalue()

                output_path.write_bytes(audio_data)
                self._cache.put(cache_key, audio_data)
            else:
                self.update_progress(0.5, "Using cached audio...")
                output_path.write_bytes(audio_data)

            self.update_progress(1.0, "Complete")

            return output_path

        except Exception as e:
            raise RuntimeError(f"ElevenLabs TTS failed: {e}") from e

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
        # If it looks like a voice ID (21 chars), use it directly
        if len(voice) == 21 and voice.isalnum():
            return voice

        # Populate voice cache if needed
        if self._voice_id_map is None:
            self.list_voices()

        voice_id_map = self._voice_id_map
        assert voice_id_map is not None, "Voice ID map should be populated"

        # Look up by name (case-insensitive)
        if voice_id := voice_id_map.get(voice.lower()):
            return voice_id

        raise ValueError(f"Voice '{voice}' not found. Use list_voices() to see available voices.")

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

    def _get_cache_key(
        self, text: str, voice_id: str, voice_settings: "VoiceSettings", format: str
    ) -> str:
        """Generate cache key for text/voice/settings/format combination."""
        data = f"elevenlabs|{text}|{voice_id}|{voice_settings}|{format}"
        return hashlib.sha256(data.encode()).hexdigest()
