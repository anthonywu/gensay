"""Local audio playback for synthesized audio bytes.

Cloud providers synthesize to bytes (for caching); playing those bytes is a
local concern shared across providers: write to a temp file, play it with the
platform player, always clean up.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


def play_audio_bytes(audio_data: bytes, suffix: str = ".mp3") -> None:
    """Play audio bytes via a temp file and the platform's CLI player.

    Currently macOS ``afplay``; raises on other platforms (callers guard by
    platform or provide their own playback).
    """
    if sys.platform != "darwin":
        raise RuntimeError(f"no audio player configured for platform {sys.platform!r}")

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            temp_path = Path(f.name)
        temp_path.write_bytes(audio_data)
        subprocess.run(["afplay", str(temp_path)], check=True)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
