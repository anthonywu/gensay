"""Local audio playback for synthesized audio bytes.

Cloud providers synthesize to bytes (for caching); playing those bytes is a
local concern shared across providers: write to a temp file, play it with the
platform player, always clean up.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path

# Players that can decode compressed audio from stdin, in preference order.
# afplay cannot read stdin, so streaming playback needs one of these installed.
_STREAM_PLAYERS: tuple[tuple[str, list[str]], ...] = (
    ("ffplay", ["-autoexit", "-nodisp", "-loglevel", "quiet", "-i", "pipe:0"]),
    ("mpv", ["--no-video", "--really-quiet", "--no-terminal", "-"]),
)


def find_stream_player() -> list[str] | None:
    """Return the argv of an installed stdin-capable audio player, or None."""
    for name, args in _STREAM_PLAYERS:
        if path := shutil.which(name):
            return [path, *args]
    return None


def stream_audio_bytes(chunks: Iterable[bytes], suffix: str = ".mp3") -> bytes:  # noqa: ARG001
    """Play audio chunks as they arrive, returning the accumulated bytes.

    Pipes chunks into a stdin-capable player (see :func:`find_stream_player`)
    so playback starts on the first chunk instead of after full synthesis.
    Callers should check ``find_stream_player()`` first and fall back to
    :func:`play_audio_bytes`; this raises ``RuntimeError`` if no player exists.

    The returned bytes are the complete audio payload (for caching). If the
    player fails mid-stream, remaining chunks are not consumed and the error
    propagates — callers must not cache on failure.
    """
    player = find_stream_player()
    if player is None:
        raise RuntimeError("no streaming audio player found (install ffmpeg or mpv)")

    buffer = bytearray()
    proc = subprocess.Popen(
        player,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert proc.stdin is not None
    try:
        for chunk in chunks:
            if not chunk:
                continue
            buffer.extend(chunk)
            proc.stdin.write(chunk)
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError(f"stream player exited with code {proc.returncode}")
    except BrokenPipeError as e:
        proc.wait()
        raise RuntimeError(f"stream player exited early (code {proc.returncode})") from e
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    return bytes(buffer)


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
