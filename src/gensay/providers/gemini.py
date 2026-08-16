"""Gemini TTS provider implementation (Gemini API native speech generation).

Uses the Gemini API ``generateContent`` batch REST endpoint with an audio
response modality (gensay is a batch/notification tool; the Live API and the
streaming Interactions surface are out of scope):

- POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent

Gemini TTS is prompt-steerable: style, accent, pace, and emotion are directed
with natural language (and inline audio tags like ``[whispers]``) rather than
request parameters. gensay exposes that as:

- ``gensay config set gemini.prompt "<style instructions>"`` — prepended to
  every request (e.g. "Say cheerfully:").
- ``-r``/``--rate`` (WPM) — translated to an inline pace instruction, since
  the API has no numeric speed parameter.
- multi-speaker dialogue (API max: 2 speakers) — ``-v 'Joe=Kore,Jane=Puck'``
  maps transcript speaker names to voices via ``multiSpeakerVoiceConfig``;
  the message text carries the dialogue ("Joe: ... Jane: ...").

The API returns raw 16-bit PCM at 24 kHz (base64), so this provider wraps it
in a WAV header; non-WAV output formats are transcoded with pydub/ffmpeg.

API key: GEMINI_API_KEY env var (GOOGLE_API_KEY also honored), else
config.extra['api_key'] (e.g. filled from OS keychain via
`gensay config set gemini.api_key`). Create keys in Google AI Studio
(https://aistudio.google.com/api-keys); prefer "auth keys" (the default for
new keys), which are scoped to the Gemini API with leaked-key enforcement —
see the "Gemini" section of USAGE.md for restriction guidance.
Default model: config.extra['model'] (e.g. `gensay config set gemini.model`),
else gemini-2.5-flash-preview-tts.
"""

from __future__ import annotations

import base64
import io
import os
import re
import wave
from typing import Any

import httpx

from .base import AudioFormat, TTSConfig
from .cloud import CloudTTSProvider, PreparedSynthesis

DEFAULT_MODEL = "gemini-2.5-flash-preview-tts"
DEFAULT_VOICE = "Kore"
API_BASE_URL = "https://generativelanguage.googleapis.com"
GENERATE_PATH_TEMPLATE = "/v1beta/models/{model}:generateContent"
PCM_SAMPLE_RATE = 24000  # documented output: 16-bit mono PCM at 24 kHz

# TTS-capable Gemini models (https://ai.google.dev/gemini-api/docs/speech-generation).
# All are prompt-steerable and support multi-speaker synthesis (up to 2
# speakers via multiSpeakerVoiceConfig — `-v 'Name=Voice,Name=Voice'`);
# only the 3.1 preview supports streaming audio generation.
KNOWN_MODELS: list[dict[str, Any]] = [
    {
        "id": "gemini-2.5-flash-preview-tts",
        "description": "Fast, cost-efficient single/multi-speaker TTS",
        "capabilities": ["multi-speaker", "prompt-steerable"],
    },
    {
        "id": "gemini-2.5-pro-preview-tts",
        "description": "Highest-quality, most expressive TTS",
        "capabilities": ["multi-speaker", "prompt-steerable"],
    },
    {
        "id": "gemini-3.1-flash-tts-preview",
        "description": "Latest preview; improved controllability and audio tags",
        "capabilities": ["multi-speaker", "prompt-steerable", "streaming"],
    },
]

# The 30 prebuilt voices, shared by all Gemini TTS models. Voices are not
# language-bound: the model auto-detects the input language (70+ supported).
_VOICES: list[tuple[str, str]] = [
    ("Zephyr", "Bright"),
    ("Puck", "Upbeat"),
    ("Charon", "Informative"),
    ("Kore", "Firm"),
    ("Fenrir", "Excitable"),
    ("Leda", "Youthful"),
    ("Orus", "Firm"),
    ("Aoede", "Breezy"),
    ("Callirrhoe", "Easy-going"),
    ("Autonoe", "Bright"),
    ("Enceladus", "Breathy"),
    ("Iapetus", "Clear"),
    ("Umbriel", "Easy-going"),
    ("Algieba", "Smooth"),
    ("Despina", "Smooth"),
    ("Erinome", "Clear"),
    ("Algenib", "Gravelly"),
    ("Rasalgethi", "Informative"),
    ("Laomedeia", "Upbeat"),
    ("Achernar", "Soft"),
    ("Alnilam", "Firm"),
    ("Schedar", "Even"),
    ("Gacrux", "Mature"),
    ("Pulcherrima", "Forward"),
    ("Achird", "Friendly"),
    ("Zubenelgenubi", "Casual"),
    ("Vindemiatrix", "Gentle"),
    ("Sadachbia", "Lively"),
    ("Sadaltager", "Knowledgeable"),
    ("Sulafat", "Warm"),
]

VOICE_CATALOG: list[dict[str, str]] = [
    {"id": name, "name": name, "description": character} for name, character in _VOICES
]

# lowercase name → canonical API voice name
_NAME_INDEX: dict[str, str] = {name.lower(): name for name, _ in _VOICES}


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw 16-bit mono PCM in a WAV container."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buffer.getvalue()


class GeminiProvider(CloudTTSProvider):
    """TTS provider using Gemini API native speech generation (batch REST)."""

    cache_namespace = "gemini"
    display_name = "Gemini"

    # Map our formats to pydub export (format, extra kwargs). WAV is native
    # (the PCM payload is wrapped in a WAV header without transcoding); the
    # rest transcode via pydub/ffmpeg. CAF has no pydub export → WAV bytes.
    FORMAT_MAP: dict[AudioFormat, tuple[str, dict[str, str]] | None] = {
        AudioFormat.WAV: None,  # native
        AudioFormat.MP3: ("mp3", {"bitrate": "192k"}),
        AudioFormat.M4A: ("mp4", {"codec": "aac", "bitrate": "192k"}),
        AudioFormat.AAC: ("adts", {"codec": "aac", "bitrate": "192k"}),
        AudioFormat.OGG: ("ogg", {}),
        AudioFormat.FLAC: ("flac", {}),
        AudioFormat.AIFF: ("aiff", {}),
        AudioFormat.CAF: None,  # no pydub export — fall back to WAV bytes
    }

    def __init__(self, config: TTSConfig | None = None):
        super().__init__(config)

        api_key: str | None = None
        self._key_source = ""
        for source, value in (
            ("GEMINI_API_KEY environment variable", os.getenv("GEMINI_API_KEY")),
            ("GOOGLE_API_KEY environment variable", os.getenv("GOOGLE_API_KEY")),
            ("configured gemini.api_key", config.extra.get("api_key") if config else None),
        ):
            if value:
                api_key, self._key_source = value, source
                break
        if not api_key:
            raise ValueError(
                "Gemini API key not found. Please set GEMINI_API_KEY environment "
                "variable or pass it in config.extra['api_key'] "
                "(e.g. via `gensay config set gemini.api_key`). "
                "Create a key at https://aistudio.google.com/api-keys"
            )
        self._http = httpx.Client(
            base_url=API_BASE_URL,
            headers={"x-goog-api-key": api_key},
            timeout=120.0,
        )
        self._default_model = (config.extra.get("model") if config else None) or DEFAULT_MODEL
        if not self._default_model.startswith("gemini-"):
            raise ValueError(
                f"Invalid Gemini model {self._default_model!r}. Expected a TTS-capable "
                f"model id like {DEFAULT_MODEL!r}; see `gensay -p gemini -v '?'`."
            )
        self._style_prompt = ((config.extra.get("prompt") if config else None) or "").strip()

    def _prepare(
        self,
        text: str,
        voice: str | None,
        rate: int | None,
        format: AudioFormat | None,
    ) -> PreparedSynthesis:
        speech_config, voice_key = self._resolve_speech_config(voice)
        model = self._default_model
        input_text = self._build_input(text, rate)
        target_format = format or AudioFormat.WAV

        def synthesize() -> bytes:
            pcm, sample_rate = self._synthesize_pcm(input_text, model, speech_config)
            wav_data = _pcm_to_wav(pcm, sample_rate)
            return self._encode(wav_data, target_format)

        return PreparedSynthesis(
            cache_parts=(input_text, model, voice_key, target_format.value),
            synthesize=synthesize,
            playback_suffix=".wav",
        )

    def list_voices(self) -> list[dict[str, Any]]:
        """List the prebuilt Gemini TTS voices (static catalog)."""
        return list(VOICE_CATALOG)

    def list_models(self) -> list[dict[str, Any]]:
        """List TTS-capable Gemini models, flagging the configured one."""
        return [{**m, "current": m["id"] == self._default_model} for m in KNOWN_MODELS]

    def get_supported_formats(self) -> list[AudioFormat]:
        """Get supported audio formats."""
        return list(self.FORMAT_MAP)

    def _resolve_speech_config(self, voice: str | None) -> tuple[dict[str, Any], str]:
        """Build the request ``speechConfig`` from a voice spec.

        Two forms are accepted:

        - single voice: ``-v Kore``
        - multi-speaker (API max: 2): ``-v 'Joe=Kore,Jane=Puck'`` — maps the
          speaker names used in the transcript ("Joe: ...") to prebuilt
          voices via ``multiSpeakerVoiceConfig``.

        Returns (speechConfig, canonical key for caching).
        """
        spec = (voice or self.config.voice or "").strip()
        if "=" not in spec:
            name = self._resolve_voice(voice)
            return {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": name}}}, name

        speakers: list[tuple[str, str]] = []
        for pair in spec.split(","):
            speaker, sep, voice_name = pair.partition("=")
            speaker = speaker.strip()
            if not sep or not speaker or not voice_name.strip():
                raise ValueError(
                    f"Invalid multi-speaker spec {spec!r}. Expected "
                    "'Speaker=Voice,Speaker=Voice' (e.g. 'Joe=Kore,Jane=Puck')."
                )
            speakers.append((speaker, self._resolve_voice(voice_name.strip())))
        if len(speakers) > 2:
            raise ValueError(
                f"Gemini TTS supports at most 2 speakers, got {len(speakers)} in {spec!r}."
            )
        config = {
            "multiSpeakerVoiceConfig": {
                "speakerVoiceConfigs": [
                    {
                        "speaker": speaker,
                        "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}},
                    }
                    for speaker, voice_name in speakers
                ]
            }
        }
        return config, ",".join(f"{s}={v}" for s, v in speakers)

    def _resolve_voice(self, voice: str | None) -> str:
        """Resolve a (case-insensitive) voice name to the canonical API name."""
        v = (voice or self.config.voice or "").strip()
        if not v:
            return DEFAULT_VOICE
        if canonical := _NAME_INDEX.get(v.lower()):
            return canonical
        raise ValueError(
            f"Voice '{voice}' not found. Pick a prebuilt Gemini voice from "
            f"`gensay -p gemini -v '?'` (e.g. {DEFAULT_VOICE!r})."
        )

    def _build_input(self, text: str, rate: int | None) -> str:
        """Compose the request text: style prompt + pace instruction + transcript.

        Gemini TTS has no numeric speed parameter; pace is steered with
        natural language, so ``-r`` becomes an inline instruction.
        """
        if rate is None:
            rate = self.config.rate
        parts = []
        if self._style_prompt:
            parts.append(self._style_prompt)
        if rate is not None:
            parts.append(f"[speak at roughly {int(rate)} words per minute]")
        parts.append(text)
        return "\n\n".join(parts)

    def _synthesize_pcm(
        self, input_text: str, model: str, speech_config: dict[str, Any]
    ) -> tuple[bytes, int]:
        """One generateContent call; returns (raw PCM bytes, sample rate).

        Retries once: the TTS models occasionally return text tokens instead
        of audio, failing the request with a 5xx or an audio-less response
        (documented behavior; Google recommends automated retry).
        """
        path = GENERATE_PATH_TEMPLATE.format(model=model)
        body = {
            "contents": [{"parts": [{"text": input_text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": speech_config,
            },
        }
        last_error: Exception | None = None
        for _attempt in range(2):
            response = self._http.post(path, json=body)
            if response.status_code >= 500:
                last_error = httpx.HTTPStatusError(
                    f"Gemini API returned {response.status_code}",
                    request=response.request,
                    response=response,
                )
                continue
            if response.status_code >= 400:
                raise RuntimeError(self._describe_client_error(response))
            try:
                return self._extract_audio(response.json())
            except ValueError as e:
                last_error = e
                continue
        raise RuntimeError(f"Gemini synthesis failed after retry: {last_error}")

    def _describe_client_error(self, response: httpx.Response) -> str:
        """Build an actionable message from a 4xx generateContent response."""
        detail = ""
        try:
            error = response.json().get("error") or {}
            detail = error.get("message") or ""
        except ValueError:
            detail = response.text[:300]
        msg = f"Gemini API returned {response.status_code}"
        if detail:
            msg += f": {detail}"
        if response.status_code in (400, 401, 403) and "key" in detail.lower():
            msg += (
                f" (credential used: {self._key_source}; note that environment "
                "variables take precedence over the keychain key set via "
                "`gensay config set gemini.api_key`)"
            )
        return msg

    @staticmethod
    def _extract_audio(payload: dict[str, Any]) -> tuple[bytes, int]:
        """Pull (PCM bytes, sample rate) out of a generateContent response."""
        candidates = payload.get("candidates") or []
        parts = (candidates[0].get("content") or {}).get("parts") if candidates else None
        pcm = b""
        sample_rate = PCM_SAMPLE_RATE
        for part in parts or []:
            inline = part.get("inlineData")
            if not inline or "data" not in inline:
                continue
            pcm += base64.b64decode(inline["data"])
            # mimeType like "audio/L16;codec=pcm;rate=24000"
            if match := re.search(r"rate=(\d+)", inline.get("mimeType", "")):
                sample_rate = int(match.group(1))
        if not pcm:
            raise ValueError(
                "response contained no audio data (the model occasionally returns "
                "text tokens instead of audio)"
            )
        return pcm, sample_rate

    def _encode(self, wav_data: bytes, format: AudioFormat) -> bytes:
        """Transcode WAV bytes to the target format (WAV/CAF pass through)."""
        export = self.FORMAT_MAP.get(format)
        if export is None:
            return wav_data
        export_format, export_kwargs = export
        from pydub import AudioSegment

        audio = AudioSegment.from_wav(io.BytesIO(wav_data))
        out = io.BytesIO()
        audio.export(out, format=export_format, **export_kwargs)
        return out.getvalue()
