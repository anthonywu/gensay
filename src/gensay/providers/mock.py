"""Mock TTS provider for testing."""

import time
from pathlib import Path
from typing import Any

from .base import AudioFormat, TTSConfig, TTSProvider


class MockProvider(TTSProvider):
    """Mock TTS provider for testing without actual TTS."""

    def __init__(self, config: TTSConfig | None = None):
        super().__init__(config)
        self.last_spoken_text = None
        self.last_saved_file = None
        self.warmup_calls = 0
        self.unload_calls = 0
        self._warm = False

    def warmup(self) -> None:
        self.warmup_calls += 1
        self._warm = True

    def unload(self) -> None:
        self.unload_calls += 1
        self._warm = False

    def speak(self, text: str, voice: str | None = None, rate: int | None = None) -> None:
        """Mock speak - just records the text."""
        self.last_spoken_text = text
        voice = voice or self.config.voice or "mock-voice"
        rate = rate or self.config.rate or 150

        self.update_progress(0.0, f"Mock speaking with {voice} at {rate} wpm")

        # Optional delay simulation (disabled when extra.simulate_delay is False)
        simulate = True
        if self.config and self.config.extra:
            simulate = self.config.extra.get("simulate_delay", True)
        if simulate:
            words = max(1, len(text.split()))
            duration = (words / rate) * 60
            steps = max(1, int(duration * 10))
            for i in range(steps):
                time.sleep(duration / steps)
                progress = (i + 1) / steps
                self.update_progress(progress, f"Speaking... {int(progress * 100)}%")
        else:
            self.update_progress(1.0, "Speaking... 100%")

        print(f"[MockProvider] Spoke: {text[:50]}...")

    def save_to_file(
        self,
        text: str,
        output_path: str | Path,
        voice: str | None = None,
        rate: int | None = None,
        format: AudioFormat | None = None,
    ) -> Path:
        """Mock save - creates a text file with metadata."""
        output_path = Path(output_path)
        self.last_saved_file = output_path

        voice = voice or self.config.voice or "mock-voice"
        rate = rate or self.config.rate or 150
        format = format or self.config.format or AudioFormat.from_extension(output_path)

        # Create mock audio file (actually a text file)
        metadata = {
            "provider": "MockProvider",
            "text": text,
            "voice": voice,
            "rate": rate,
            "format": format.value,
            "length": len(text),
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(str(metadata))

        self.update_progress(1.0, f"Saved to {output_path.name}")

        return output_path

    def list_voices(self) -> list[dict[str, Any]]:
        """List mock voices."""
        return [
            {
                "id": "mock-voice-1",
                "name": "Mock Voice 1",
                "language": "en-US",
                "gender": "neutral",
            },
            {"id": "mock-voice-2", "name": "Mock Voice 2", "language": "en-GB", "gender": "female"},
            {"id": "mock-voice-3", "name": "Mock Voice 3", "language": "es-ES", "gender": "male"},
        ]

    def get_supported_formats(self) -> list[AudioFormat]:
        """Mock supports all formats."""
        return list(AudioFormat)
