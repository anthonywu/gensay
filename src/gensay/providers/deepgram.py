"""Deepgram TTS provider implementation (Flux, Aura-2, Aura model families).

Uses the batch REST transports (gensay is a batch/notification tool, not a
conversational agent, so the streaming WebSocket surface is out of scope):

- Flux voices  → POST https://api.deepgram.com/v2/speak?model=flux-{voice}-{lang}
- Aura/Aura-2  → POST https://api.deepgram.com/v1/speak?model=aura(-2)-{voice}-{lang}

Deepgram embeds the voice in the ``model`` query parameter rather than a
request field, so ``-v <voice>`` resolves to a full model string: short names
(e.g. ``haley``) resolve from the static catalog (Flux first, then Aura-2,
then Aura); full model strings (e.g. ``flux-haley-en``) pass through as-is.

API key: DEEPGRAM_API_KEY env var, else config.extra['api_key']
(e.g. filled from OS keychain via `gensay config set deepgram.api_key`;
keychain storage needs the 'gensay[deepgram]' extra, which adds keyring).
Default model: config.extra['model'] (e.g. `gensay config set deepgram.model`),
else flux-haley-en.
"""

from typing import Any

import httpx

from .base import AudioFormat, TTSConfig
from .cloud import CloudTTSProvider, PreparedSynthesis

DEFAULT_MODEL = "flux-haley-en"
API_BASE_URL = "https://api.deepgram.com"
V2_SPEAK_PATH = "/v2/speak"
V1_SPEAK_PATH = "/v1/speak"

# Flux voices (documented at https://developers.deepgram.com/docs/flux-tts/voices)
# English-only at GA; accent spans American/British/Irish/Australian/Indian/
# Singaporean/Filipino English.
_FLUX_VOICES: list[dict[str, str]] = [
    # Featured voices
    {"name": "Hannah", "accent": "American", "gender": "Female", "character": "clear, confident"},
    {"name": "Kit", "accent": "British", "gender": "Male", "character": "friendly, calm"},
    {"name": "Alexis", "accent": "American", "gender": "Female", "character": "professional, calm"},
    {"name": "Cliff", "accent": "American", "gender": "Male", "character": "deep, confident"},
    {"name": "Sienna", "accent": "American", "gender": "Female", "character": "professional, warm"},
    {"name": "Cole", "accent": "American", "gender": "Male", "character": "friendly, clear"},
    {
        "name": "Brooke",
        "accent": "American",
        "gender": "Female",
        "character": "friendly, energetic",
    },
    {"name": "Colin", "accent": "British", "gender": "Male", "character": "warm, trustworthy"},
    {"name": "Gemma", "accent": "British", "gender": "Female", "character": "friendly, kind"},
    {
        "name": "Haley",
        "accent": "American",
        "gender": "Female",
        "character": "professional, caring",
    },
    {"name": "Heather", "accent": "American", "gender": "Female", "character": "clear, engaging"},
    {"name": "Miles", "accent": "American", "gender": "Male", "character": "calm, professional"},
    {"name": "Sean", "accent": "British", "gender": "Male", "character": "friendly, kind"},
    # More voices
    {"name": "Bree", "accent": "American", "gender": "Female", "character": "friendly, sweet"},
    {"name": "Brittany", "accent": "American", "gender": "Female", "character": "confident, soft"},
    {"name": "Bruce", "accent": "American", "gender": "Male", "character": "friendly, natural"},
    {"name": "Conor", "accent": "British", "gender": "Male", "character": "confident, relaxed"},
    {"name": "Donovan", "accent": "American", "gender": "Male", "character": "professional, calm"},
    {"name": "Drew", "accent": "American", "gender": "Male", "character": "confident, relaxed"},
    {"name": "Elise", "accent": "American", "gender": "Female", "character": "clear, professional"},
    {"name": "Jack", "accent": "British", "gender": "Male", "character": "confident, thoughtful"},
    {"name": "Kai", "accent": "Singaporean", "gender": "Male", "character": "clear, calm"},
    {"name": "Kelsey", "accent": "American", "gender": "Female", "character": "clear, caring"},
    {"name": "Maeve", "accent": "Irish", "gender": "Female", "character": "friendly, energetic"},
    {"name": "Marcelo", "accent": "Filipino", "gender": "Male", "character": "clear, calm"},
    {"name": "Marcus", "accent": "American", "gender": "Male", "character": "friendly, smooth"},
    {"name": "Meena", "accent": "Indian", "gender": "Female", "character": "empathetic, calm"},
    {
        "name": "Meghan",
        "accent": "American",
        "gender": "Female",
        "character": "friendly, energetic",
    },
    {"name": "Naveen", "accent": "Indian", "gender": "Male", "character": "clear, knowledgeable"},
    {"name": "Paige", "accent": "American", "gender": "Female", "character": "clear, comfortable"},
    {"name": "Priya", "accent": "Indian", "gender": "Female", "character": "confident, empathetic"},
    {"name": "Rufus", "accent": "British", "gender": "Male", "character": "friendly, confident"},
    {"name": "Sharon", "accent": "Australian", "gender": "Female", "character": "formal, calm"},
    {"name": "Tanner", "accent": "British", "gender": "Male", "character": "professional, calm"},
    {"name": "Wade", "accent": "American", "gender": "Male", "character": "warm, confident"},
    {"name": "Wes", "accent": "American", "gender": "Male", "character": "thoughtful, friendly"},
]

# Aura (v1) voices — model strings from the v1/speak API reference enum.
_AURA_VOICE_NAMES_EN = [
    "angus",
    "arcas",
    "asteria",
    "athena",
    "helios",
    "hera",
    "luna",
    "orion",
    "orpheus",
    "perseus",
    "stella",
    "zeus",
]

# Aura-2 voices by language suffix (v1/speak API reference enum).
_AURA2_VOICE_NAMES: dict[str, list[str]] = {
    "en": [
        "amalthea",
        "andromeda",
        "apollo",
        "arcas",
        "aries",
        "asteria",
        "athena",
        "atlas",
        "aurora",
        "callista",
        "cora",
        "cordelia",
        "delia",
        "draco",
        "electra",
        "harmonia",
        "helena",
        "hera",
        "hermes",
        "hyperion",
        "iris",
        "janus",
        "juno",
        "jupiter",
        "luna",
        "mars",
        "minerva",
        "neptune",
        "odysseus",
        "ophelia",
        "orion",
        "orpheus",
        "pandora",
        "phoebe",
        "pluto",
        "saturn",
        "selene",
        "thalia",
        "theia",
        "vesta",
        "zeus",
    ],
    "es": [
        "agustina",
        "alvaro",
        "antonia",
        "aquila",
        "carina",
        "celeste",
        "diana",
        "estrella",
        "gloria",
        "javier",
        "luciano",
        "nestor",
        "olivia",
        "selena",
        "silvia",
        "sirio",
        "valerio",
    ],
    "de": ["aurelia", "elara", "fabian", "julius", "kara", "lara", "viktoria"],
    "nl": ["beatrix", "cornelia", "daphne", "hestia", "lars", "leda", "rhea", "roman", "sander"],
    "fr": ["agathe", "hector"],
    "it": [
        "cesare",
        "cinzia",
        "demetra",
        "dionisio",
        "elio",
        "flavio",
        "livia",
        "maia",
        "melia",
        "perseo",
    ],
    "ja": ["ama", "ebisu", "fujin", "izanami", "uzume"],
}


def _build_voice_catalog() -> list[dict[str, str]]:
    """Static voice catalog (Deepgram has no voices-list API; models are the voice)."""
    catalog: list[dict[str, str]] = []
    for v in _FLUX_VOICES:
        catalog.append(
            {
                "id": f"flux-{v['name'].lower()}-en",
                "name": v["name"],
                "language": "en",
                "family": "flux",
                "accent": v["accent"],
                "gender": v["gender"],
                "description": v["character"],
            }
        )
    for name in _AURA_VOICE_NAMES_EN:
        catalog.append(
            {
                "id": f"aura-{name}-en",
                "name": name.capitalize(),
                "language": "en",
                "family": "aura",
                "description": "Aura voice (legacy; superseded by Aura-2)",
            }
        )
    for lang, names in _AURA2_VOICE_NAMES.items():
        for name in names:
            catalog.append(
                {
                    "id": f"aura-2-{name}-{lang}",
                    "name": name.capitalize(),
                    "language": lang,
                    "family": "aura-2",
                    "description": "Aura-2 voice",
                }
            )
    return catalog


VOICE_CATALOG: list[dict[str, str]] = _build_voice_catalog()

# short name (lowercase) → model string. Newer family wins on name collisions
# (e.g. "asteria" exists in aura and aura-2 → aura-2): last overwrite wins.
_NAME_INDEX: dict[str, str] = {}
for _entry in sorted(VOICE_CATALOG, key=lambda e: {"aura": 0, "aura-2": 1, "flux": 2}[e["family"]]):
    _NAME_INDEX[_entry["name"].lower()] = _entry["id"]


class DeepgramProvider(CloudTTSProvider):
    """TTS provider using Deepgram's batch REST API (Flux and Aura model families)."""

    cache_namespace = "deepgram"
    display_name = "Deepgram"

    # Map our formats to Deepgram (encoding, container) request params.
    # Container omitted unless it must disambiguate (wav for raw linear16, ogg for opus).
    FORMAT_MAP = {
        AudioFormat.MP3: ("mp3", None),
        AudioFormat.OGG: ("opus", "ogg"),
        AudioFormat.FLAC: ("flac", None),
        AudioFormat.AAC: ("aac", None),
        AudioFormat.M4A: ("aac", None),  # ADTS AAC; afplay/iTunes play it fine
        AudioFormat.WAV: ("linear16", "wav"),
        # No native AIFF/CAF — use MP3 like the other cloud providers
        AudioFormat.AIFF: ("mp3", None),
        AudioFormat.CAF: ("mp3", None),
    }

    def __init__(self, config: TTSConfig | None = None):
        super().__init__(config)

        api_key = self.resolve_api_key(
            "DEEPGRAM_API_KEY",
            config,
            display_name="Deepgram",
            config_hint="(e.g. via `gensay config set deepgram.api_key`)",
        )
        self._http = httpx.Client(
            base_url=API_BASE_URL,
            headers={"Authorization": f"Token {api_key}"},
            timeout=60.0,
        )
        self._default_model = (
            (config.extra.get("model") if config else None) or DEFAULT_MODEL
        ).lower()
        if not self._default_model.startswith(("flux-", "aura-")):
            raise ValueError(
                f"Invalid Deepgram model {self._default_model!r}. Deepgram models are "
                f"full voice strings like {DEFAULT_MODEL!r}; see `gensay -p deepgram -v '?'`."
            )

    def _prepare(
        self,
        text: str,
        voice: str | None,
        rate: int | None,
        format: AudioFormat | None,
    ) -> PreparedSynthesis:
        model = self._resolve_model(voice)
        speed = self._rate_to_speed(model, rate)
        if format is None:
            encoding, container = "mp3", None
        else:
            encoding, container = self.FORMAT_MAP.get(format, ("mp3", None))

        def synthesize() -> bytes:
            return self._synthesize(text, model, encoding, container, speed)

        return PreparedSynthesis(
            cache_parts=(text, model, speed, encoding, container),
            synthesize=synthesize,
        )

    def list_voices(self) -> list[dict[str, Any]]:
        """List available Deepgram TTS voices (static — models are the voices)."""
        return list(VOICE_CATALOG)

    def get_supported_formats(self) -> list[AudioFormat]:
        """Get supported audio formats."""
        return list(self.FORMAT_MAP)

    def _resolve_model(self, voice: str | None) -> str:
        """Resolve a voice short name or full model string to a model string."""
        if not voice and not self.config.voice:
            return self._default_model

        v = (voice or self.config.voice or "").strip().lower()
        if v.startswith(("flux-", "aura-")):
            return v  # caller passed a full model string

        if model := _NAME_INDEX.get(v):
            return model

        raise ValueError(
            f"Voice '{voice}' not found. Pass a full model string (e.g. {DEFAULT_MODEL!r}) "
            f"or a short name from `gensay -p deepgram -v '?'`."
        )

    def _rate_to_speed(self, model: str, rate: int | None) -> float | None:
        """Convert WPM rate to Deepgram speed multiplier (None → omit the param).

        Flux REST accepts only {0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15};
        Aura accepts a continuous double (clamped here to 0.5–2.0).
        """
        if rate is None:
            rate = self.config.rate
        if rate is None:
            return None

        speed = rate / 150.0  # ~150 WPM is normal
        if model.startswith("flux-"):
            snapped = round(max(0.85, min(1.15, speed)) / 0.05) * 0.05
            return round(snapped, 2)
        return round(max(0.5, min(2.0, speed)), 2)

    def _synthesize(
        self,
        text: str,
        model: str,
        encoding: str,
        container: str | None,
        speed: float | None,
    ) -> bytes:
        """One batch REST call; returns the full audio payload."""
        path = V2_SPEAK_PATH if model.startswith("flux-") else V1_SPEAK_PATH

        params: dict[str, Any] = {"model": model, "encoding": encoding}
        if container:
            params["container"] = container
        if speed is not None:
            params["speed"] = speed

        response = self._http.post(path, params=params, json={"text": text})
        response.raise_for_status()
        return response.content
