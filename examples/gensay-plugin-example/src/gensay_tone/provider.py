"""ToneProvider: renders text as sine-wave tones. Stdlib only.

Not useful speech, but a complete, offline TTSProvider implementation you
can hear — each character becomes a short pitched beep. Demonstrates the
full provider surface: speak, save_to_file, list_voices,
get_supported_formats, config (voice/rate), and progress reporting.
"""

from __future__ import annotations

import io
import math
import struct
import wave
from pathlib import Path
from typing import Any

from gensay.plugin import AudioFormat, TTSConfig, TTSProvider, play_audio_bytes

SAMPLE_RATE = 22050

#: voice name -> base frequency in Hz
VOICES = {"low": 220.0, "mid": 440.0, "high": 880.0}
DEFAULT_VOICE = "mid"
DEFAULT_RATE_WPM = 180  # maps to note duration below


class ToneProvider(TTSProvider):
    """Beeps out text, one tone per character."""

    def __init__(self, config: TTSConfig | None = None):
        super().__init__(config)

    # -- required interface -------------------------------------------------

    def speak(self, text: str, voice: str | None = None, rate: int | None = None) -> None:
        audio = self._render_wav(text, voice, rate)
        self.update_progress(0.9, "Playing")
        play_audio_bytes(audio, suffix=".wav")
        self.update_progress(1.0, "Done")

    def save_to_file(
        self,
        text: str,
        output_path: str | Path,
        voice: str | None = None,
        rate: int | None = None,
        format: AudioFormat | None = None,
    ) -> Path:
        format = format or AudioFormat.from_extension(output_path)
        if format is not AudioFormat.WAV:
            raise ValueError(f"gensay-tone only writes WAV, not {format.value}")
        path = Path(output_path)
        path.write_bytes(self._render_wav(text, voice, rate))
        self.update_progress(1.0, "Done")
        return path

    def list_voices(self) -> list[dict[str, Any]]:
        return [
            {
                "id": name,
                "name": name,
                "language": "none",
                "description": f"sine tones around {hz:g} Hz",
            }
            for name, hz in VOICES.items()
        ]

    def get_supported_formats(self) -> list[AudioFormat]:
        return [AudioFormat.WAV]

    # -- synthesis -----------------------------------------------------------

    def _render_wav(self, text: str, voice: str | None, rate: int | None) -> bytes:
        base_hz = VOICES.get(voice or self.config.voice or DEFAULT_VOICE, VOICES[DEFAULT_VOICE])
        wpm = rate or self.config.rate or DEFAULT_RATE_WPM
        # One "word" ~ 5 chars; note duration so chars/minute matches wpm * 5.
        note_seconds = max(0.02, 60.0 / (wpm * 5))

        frames = bytearray()
        chars = text or " "
        for i, ch in enumerate(chars):
            self.update_progress(0.8 * i / len(chars), "Synthesizing")
            if ch.isspace():
                frames += self._silence(note_seconds)
            else:
                # Pitch each character within one octave of the base.
                freq = base_hz * 2 ** ((ord(ch) % 12) / 12)
                frames += self._sine(freq, note_seconds)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(bytes(frames))
        return buf.getvalue()

    @staticmethod
    def _sine(freq: float, seconds: float) -> bytes:
        n = int(SAMPLE_RATE * seconds)
        out = bytearray()
        for i in range(n):
            # Short linear fade in/out to avoid clicks between notes.
            envelope = min(1.0, i / 100, (n - i) / 100)
            sample = int(12000 * envelope * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
            out += struct.pack("<h", sample)
        return bytes(out)

    @staticmethod
    def _silence(seconds: float) -> bytes:
        return b"\x00\x00" * int(SAMPLE_RATE * seconds)
