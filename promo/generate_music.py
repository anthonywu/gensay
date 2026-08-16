#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.28", "python-dotenv>=1.1", "keyring>=25.0"]
# ///
"""Generate the sizzle reel's background music via the ElevenLabs Music API.

Writes remotion/public/music.mp3 (30s instrumental). Skips generation if the
file already exists; pass --force to regenerate. Requires ELEVENLABS_API_KEY
(paid plan — the Music API is not on the free tier).
"""

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

REEL_LENGTH_MS = 30_000
OUT = Path(__file__).parent / "remotion" / "public" / "music.mp3"

PROMPT = (
    "Minimal, modern tech product launch background music. Upbeat electronic, "
    "clean synth arpeggios, warm bass, soft four-on-the-floor percussion, "
    "optimistic and confident, steadily building energy, then a clean resolve "
    "at the end. Instrumental only, no vocals. Suitable as quiet background "
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


def main() -> int:
    load_dotenv(Path(__file__).parent.parent / ".env")
    api_key = _api_key()
    if not api_key:
        print(
            "error: no ElevenLabs key (set ELEVENLABS_API_KEY or "
            "`gensay config set elevenlabs.api_key`)",
            file=sys.stderr,
        )
        return 1

    if OUT.exists() and "--force" not in sys.argv:
        print(f"{OUT} already exists; pass --force to regenerate")
        return 0

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

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(resp.content)
    print(f"✓ wrote {OUT} ({len(resp.content) / 1024:.0f} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
