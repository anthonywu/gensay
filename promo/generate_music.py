#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.28", "python-dotenv>=1.1", "keyring>=25.0", "ffmpeg-normalize>=1.28"]
# ///
"""Generate the sizzle reel's background music via the ElevenLabs Music API.

The raw API response is cached as music_raw.mp3 (re-runs don't re-spend
credits), then trimmed to 30s and loudness-normalized via ffmpeg-normalize
into remotion/public/music.mp3. The prompt asks for constant energy with no
intro build or outro fade — sanity-check a regenerated track with a
per-second RMS profile before shipping. Skips generation if the raw file
already exists; pass --force to regenerate. Requires ELEVENLABS_API_KEY
(paid plan — the Music API is not on the free tier).
"""

import os
import subprocess
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

REEL_LENGTH_MS = 30_000
RAW = Path(__file__).parent / "music_raw.mp3"
OUT = Path(__file__).parent / "remotion" / "public" / "music.mp3"

PROMPT = (
    "Minimal, modern tech product launch background music. Upbeat electronic, "
    "clean synth arpeggios, warm bass, soft four-on-the-floor percussion, "
    "optimistic and confident. Starts instantly at full energy on the very "
    "first beat — no intro, no build-up, no fade-in. Keeps constant energy "
    "and loudness for the entire duration, all the way to the final second — "
    "no outro, no wind-down, no fade-out (the video edit handles all fades). "
    "Instrumental only, no vocals. Suitable as a continuous background loop "
    "under a 30-second software demo video."
)


def _api_key() -> str | None:
    """Same precedence as gensay: env var, then OS keychain (service 'gensay')."""
    if key := os.environ.get("ELEVENLABS_API_KEY"):
        return key
    try:
        import keyring

        return keyring.get_password("gensay", "elevenlabs.api_key")
    except Exception:
        return None


def smooth(raw: Path, out: Path) -> None:
    """Trim to reel length and pin overall loudness to -18 LUFS."""
    subprocess.run(
        [
            "ffmpeg-normalize",
            str(raw),
            "-o",
            str(out),
            "-f",  # overwrite
            "-prf",
            f"atrim=0:{REEL_LENGTH_MS / 1000:.0f}",
            "-t",
            "-18",
            "-tp",
            "-1.5",
            "-ar",
            "44100",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
        ],
        check=True,
        timeout=120,
    )


def main() -> int:
    load_dotenv(Path(__file__).parent.parent / ".env")

    if RAW.exists() and "--force" not in sys.argv:
        print(f"{RAW} already exists; pass --force to regenerate")
    else:
        api_key = _api_key()
        if not api_key:
            print(
                "error: no ElevenLabs key (set ELEVENLABS_API_KEY or "
                "`gensay config set elevenlabs.api_key`)",
                file=sys.stderr,
            )
            return 1

        print(f"Generating {REEL_LENGTH_MS / 1000:.0f}s instrumental via ElevenLabs Music API...")
        resp = httpx.post(
            "https://api.elevenlabs.io/v1/music",
            headers={"xi-api-key": api_key},
            json={
                "prompt": PROMPT,
                "music_length_ms": REEL_LENGTH_MS,
                "model_id": "music_v2",
                "force_instrumental": True,
            },
            timeout=300,
        )
        if resp.status_code != 200:
            print(f"error: HTTP {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
            return 1
        RAW.write_bytes(resp.content)
        print(f"✓ wrote {RAW} ({len(resp.content) / 1024:.0f} KiB)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    smooth(RAW, OUT)
    print(f"✓ smoothed → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
