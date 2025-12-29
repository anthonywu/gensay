"""macOS native say command wrapper provider."""

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..cache import TTSCache
from .base import AudioFormat, TTSConfig, TTSProvider


class MacOSSayProvider(TTSProvider):
    """TTS provider wrapping macOS /usr/bin/say command."""

    def __init__(self, config: TTSConfig | None = None):
        super().__init__(config)
        self._say_path = "/usr/bin/say"
        self._cache = TTSCache(enabled=config.cache_enabled if config else True)

        # Check if we're on macOS
        if sys.platform != "darwin":
            raise RuntimeError("macOS say command is only available on macOS")

        # Check if say command exists
        if not Path(self._say_path).exists():
            raise RuntimeError("macOS say command not found")

    def speak(self, text: str, voice: str | None = None, rate: int | None = None) -> None:
        """Speak text using macOS say command."""
        cmd = [self._say_path]

        if voice or self.config.voice:
            cmd.extend(["-v", voice or self.config.voice])

        if rate or self.config.rate:
            cmd.extend(["-r", str(rate or self.config.rate)])

        cmd.append(text)

        try:
            self.update_progress(0.0, "Speaking...")
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.update_progress(1.0, "Complete")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"say command failed: {e.stderr}") from e

    def save_to_file(
        self,
        text: str,
        output_path: str | Path,
        voice: str | None = None,
        rate: int | None = None,
        format: AudioFormat | None = None,
    ) -> Path:
        """Save speech to file using macOS say command."""
        output_path = Path(output_path)
        format = format or self.config.format or AudioFormat.from_extension(output_path)

        cmd = [self._say_path]

        if voice or self.config.voice:
            cmd.extend(["-v", voice or self.config.voice])

        if rate or self.config.rate:
            cmd.extend(["-r", str(rate or self.config.rate)])

        cmd.extend(["-o", str(output_path)])

        # Add format-specific options
        if format == AudioFormat.M4A:
            cmd.extend(["--data-format=aac"])
        elif format == AudioFormat.WAV:
            cmd.extend(["--file-format=WAVE"])

        cmd.append(text)

        try:
            self.update_progress(0.0, "Generating audio...")
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.update_progress(1.0, "Complete")
            return output_path
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"say command failed: {e.stderr}") from e

    def list_voices(self) -> list[dict[str, Any]]:
        """List available macOS voices."""
        cmd = [self._say_path, "-v", "?"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            voices = []

            for line in result.stdout.strip().split("\n"):
                if line:
                    # Parse voice line format: "Name Language # Comment"
                    parts = line.split(maxsplit=2)
                    if len(parts) >= 2:
                        voice_id = parts[0]
                        language = parts[1]
                        comment = parts[2] if len(parts) > 2 else ""

                        voices.append(
                            {
                                "id": voice_id,
                                "name": voice_id,
                                "language": language,
                                "description": comment.lstrip("# "),
                                "gender": self._guess_gender(voice_id),
                            }
                        )

            return voices
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to list voices: {e.stderr}") from e

    def get_supported_formats(self) -> list[AudioFormat]:
        """Get supported audio formats."""
        # macOS say supports many formats
        return [
            AudioFormat.AIFF,
            AudioFormat.WAV,
            AudioFormat.M4A,
            AudioFormat.CAF,
            AudioFormat.AAC,
        ]

    def _guess_gender(self, voice_name: str) -> str:
        """Guess gender from voice name."""
        # Common patterns in macOS voice names
        female_names = ["samantha", "victoria", "karen", "fiona", "moira", "tessa"]
        male_names = ["alex", "daniel", "oliver", "thomas", "lee", "rishi"]

        voice_lower = voice_name.lower()
        if any(name in voice_lower for name in female_names):
            return "female"
        elif any(name in voice_lower for name in male_names):
            return "male"
        else:
            return "neutral"

    def _get_cache_key(self, text: str, voice: str | None = None, rate: int | None = None) -> str:
        """Generate cache key for text/voice/rate combination."""
        voice = voice or self.config.voice or "default"
        rate = rate or self.config.rate or 200
        data = f"macos|{text}|{voice}|{rate}"
        return hashlib.sha256(data.encode()).hexdigest()
