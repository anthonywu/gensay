# gensay sizzle reel

Code-backed 30-second release reel. Terminal demos are recorded with
[VHS](https://github.com/charmbracelet/vhs) from `.tape` scripts; the final
video is composited with [Remotion](https://remotion.dev) (React).

## Regenerate

Recipes live in `promo/justfile` — run as `just <recipe>` from this
directory, or `just promo::<recipe>` from the repo root:

```bash
just sizzle    # record tapes + generate voices + render video
# or step by step:
just tapes     # vhs tapes/*.tape → remotion/public/clips/*.mp4
just voices    # gensay per provider → loudness-normalized remotion/public/voices/*.mp3
just music     # ElevenLabs Music API → remotion/public/music.mp3 (optional)
just render    # remotion render → promo/out/gensay-sizzle.mp4
just studio    # live-edit the composition in the browser
```

Background music is optional: if `remotion/public/music.mp3` exists it is
mixed in with a fade in/out and ducked under the provider voice lines;
otherwise the reel renders without music. `just music` calls the ElevenLabs
Music API (`ELEVENLABS_API_KEY`, paid plan required) and skips if the file
already exists — pass `--force` to roll a new track.

`just voices` has every provider introduce itself through `gensay` (cloud
providers need their API keys; local models must be cached). Raw synthesis is
kept in `voices_raw/` so re-runs don't re-spend API credits; each clip is
loudness-normalized to -16 LUFS via ffmpeg-normalize. Voice timing/ducking:
`remotion/src/voiceSchedule.ts` (data-driven from `voice-durations.json`).

Requirements: `vhs`, `ffmpeg`, Node 20+, and a working `gensay` on PATH
(tapes run real commands against the `macos`, `gemini` voice-list, and
`mock` providers — no API keys needed).

## Editing for the next release

- Scene timings and copy: `remotion/src/SizzleReel.tsx` (900 frames = 30s @ 30fps)
- Terminal demos: `tapes/*.tape` — re-run `just tapes` after editing
- Voice roll-call lines: `generate_voices.py` — re-run `just voices --force`
- Provider grid / feature ticker: `remotion/src/scenes/ProvidersGrid.tsx`, `Closing.tsx`
- Colors/fonts: `remotion/src/theme.ts`
