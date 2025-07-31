"""ElevenLabs TTS provider implementation."""

import os
from pathlib import Path
from typing import Any

try:
    from elevenlabs import VoiceSettings, play, save
    from elevenlabs.client import ElevenLabs

    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False

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
                "ElevenLabs library not found. Please install it with: "
                "pip install 'elevenlabs[pyaudio]'"
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
        self._voice_cache = None  # Cache for voice list

    def speak(self, text: str, voice: str | None = None, rate: int | None = None) -> None:
        """Speak text using ElevenLabs TTS."""
        voice = voice or self.config.voice or "Rachel"  # Default ElevenLabs voice

        # Get voice settings
        voice_settings = self._get_voice_settings(rate)

        try:
            self.update_progress(0.0, "Generating speech...")

            # Generate audio
            audio = self.client.generate(
                text=text,
                voice=voice,
                voice_settings=voice_settings,
                model="eleven_monolingual_v1",  # You can make this configurable
            )

            self.update_progress(0.5, "Playing audio...")

            # Play the audio
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
        voice = voice or self.config.voice or "Rachel"
        format = format or self.config.format or AudioFormat.from_extension(output_path)

        # Get voice settings
        voice_settings = self._get_voice_settings(rate)

        # Map format to ElevenLabs format
        el_format = self.FORMAT_MAP.get(format, "mp3_44100_128")

        try:
            self.update_progress(0.0, "Generating speech...")

            # Generate audio with specific format
            audio = self.client.generate(
                text=text,
                voice=voice,
                voice_settings=voice_settings,
                model="eleven_monolingual_v1",
                output_format=el_format,
            )

            self.update_progress(0.5, "Saving to file...")

            # Save the audio
            save(audio, str(output_path))

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

                for voice in response.voices:
                    voice_data = {
                        "id": voice.voice_id,
                        "name": voice.name,
                        "language": "en-US",  # ElevenLabs voices are multilingual
                        "category": voice.category,
                    }

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

    def _get_voice_settings(self, rate: int | None = None) -> VoiceSettings:
        """Get voice settings with optional rate adjustment."""
        # ElevenLabs doesn't directly support WPM, but we can adjust stability/speed
        # Higher stability = slower, more careful speech
        # Lower stability = faster, more expressive speech

        if rate:
            # Map WPM to stability (inverse relationship)
            # Normal rate ~150 WPM = 0.5 stability
            # Fast rate ~200 WPM = 0.3 stability
            # Slow rate ~100 WPM = 0.7 stability
            stability = max(0.0, min(1.0, 1.0 - (rate - 100) / 200))
        else:
            stability = 0.5  # Default

        return VoiceSettings(
            stability=stability,
            similarity_boost=0.75,  # Default similarity
            style=0.0,  # Default style
            use_speaker_boost=True,
        )
