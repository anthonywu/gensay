#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ffmpeg-normalize>=1.28"]
# ///
"""Generate the provider roll-call voice lines for the sizzle reel.

Each provider synthesizes its own short intro via `gensay -o`, dogfooding the
tool itself. Local AI providers (chatterbox, vibevoice) and cloud providers
run through the repo venv (`uv run gensay`) which has all extras installed.

Raw synthesis output lands in promo/voices_raw/ (so re-runs don't re-spend
API credits), then each clip is loudness-normalized (EBU R128, -16 LUFS) via
ffmpeg into remotion/public/voices/<provider>.mp3 so provider volumes match
when stitched together. Also writes remotion/src/voice-durations.json
(ordered, with durations via ffprobe).
Skips providers whose raw file already exists; --force regenerates everything.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

PROMO = Path(__file__).parent
REPO = PROMO.parent
RAW_DIR = PROMO / "voices_raw"
VOICES_DIR = PROMO / "remotion" / "public" / "voices"
OUT_JSON = PROMO / "remotion" / "src" / "voice-durations.json"

# Roll-call order: local column top-to-bottom, then cloud column.
# Format note: the macos provider currently writes broken mp3 files
# (16-byte header only), so it gets m4a; everything else does mp3 natively.
LINES: list[tuple[str, str, str]] = [
    ("macos", "Classic Mac O S say, built in.", "m4a"),
    ("vibevoice", "VibeVoice, on device.", "mp3"),
    ("chatterbox", "Chatterbox, running locally.", "mp3"),
    ("elevenlabs", "ElevenLabs here.", "mp3"),
    ("deepgram", "Deepgram, ready.", "mp3"),
    ("gemini", "This is Google Gemini.", "mp3"),
    ("openai", "OpenAI, checking in.", "mp3"),
    ("polly", "Polly, from Amazon.", "mp3"),
]


def synthesize(provider: str, line: str, fmt: str, out: Path) -> None:
    cmd = [
        "uv",
        "run",
        "gensay",
        "-p",
        provider,
        "-o",
        str(out),
        "--format",
        fmt,
        "--no-progress",
        "--no-daemon",  # don't collide with any running warm daemon
        line,
    ]
    print(f"[{provider}] {line!r}")
    # Clean config: suppress personal defaults (e.g. a configured elevenlabs
    # voice) without losing keychain-stored API keys.
    env = {**os.environ, "GENSAY_CONFIG": "/tmp/gensay-sizzle-noconfig.toml"}
    # Polly needs a region; mirror AWS_REGION into AWS_DEFAULT_REGION for boto.
    region = env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or "us-west-2"
    env.setdefault("AWS_DEFAULT_REGION", region)
    env.setdefault("AWS_REGION", region)
    subprocess.run(cmd, cwd=REPO, check=True, timeout=600, env=env)


TARGET_LUFS = -16.0
TARGET_TP_DB = -1.5


def normalize(raw: Path, out: Path) -> None:
    """Loudness-normalize to -16 LUFS / -1.5 dBTP via ffmpeg-normalize.

    The compressor pre-filter tames crest-heavy clips (chatterbox, vibevoice)
    so they can reach the integrated-loudness target without being gain-capped
    by the true-peak ceiling.
    """
    subprocess.run(
        [
            "ffmpeg-normalize",
            str(raw),
            "-o",
            str(out),
            "-f",  # overwrite
            "--dynamic",
            "-prf",
            "acompressor=threshold=-22dB:ratio=9:attack=1:release=120:makeup=8dB",
            "-t",
            str(TARGET_LUFS),
            "-tp",
            str(TARGET_TP_DB),
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


def duration_s(path: Path) -> float | None:
    """Duration in seconds, or None if the file is missing/unreadable."""
    if not path.exists():
        return None
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        return None
    try:
        return float(out.stdout.strip())
    except ValueError:
        return None


def main() -> int:
    force = "--force" in sys.argv
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    VOICES_DIR.mkdir(parents=True, exist_ok=True)

    entries = []
    failures = []
    for provider, line, fmt in LINES:
        raw = RAW_DIR / f"{provider}.{fmt}"
        out = VOICES_DIR / f"{provider}.mp3"
        if force or duration_s(raw) is None:
            raw.unlink(missing_ok=True)
            try:
                synthesize(provider, line, fmt, raw)
            except subprocess.CalledProcessError:
                print(f"[{provider}] synthesis failed", file=sys.stderr)
        else:
            print(f"[{provider}] raw exists, skipping (use --force to regenerate)")
        if duration_s(raw) is None:
            failures.append(provider)
            continue
        if force or duration_s(out) is None or raw.stat().st_mtime > out.stat().st_mtime:
            normalize(raw, out)
        secs = duration_s(out)
        if secs is None:
            failures.append(provider)
            continue
        entries.append({"id": provider, "file": f"voices/{provider}.mp3", "seconds": secs})

    # Write whatever succeeded so the reel can build; missing providers are
    # simply not scheduled. Exit nonzero if any failed.
    OUT_JSON.write_text(json.dumps(entries, indent=2) + "\n")
    total = sum(e["seconds"] for e in entries)
    print(f"✓ {len(entries)}/{len(LINES)} voices, {total:.1f}s total → {OUT_JSON}")
    if failures:
        print(f"✗ missing/invalid audio for: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
