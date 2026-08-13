"""Unit tests for ElevenLabsProvider with a stubbed SDK client (no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gensay.providers.base import AudioFormat, TTSConfig
from gensay.providers.elevenlabs import DEFAULT_MODEL, ElevenLabsProvider

FAKE_AUDIO = b"\xff\xfb" + b"x" * 128  # fake mp3 frames


class FakeTTS:
    def __init__(self, audio: bytes = FAKE_AUDIO):
        self.audio = audio
        self.calls: list[dict] = []
        self.should_raise: Exception | None = None

    def convert(self, **kwargs):
        self.calls.append(kwargs)
        if self.should_raise:
            raise self.should_raise
        return iter([self.audio])


class FakeVoices:
    def __init__(self, voices):
        self._voices = voices
        self.get_all_calls = 0

    def get_all(self):
        self.get_all_calls += 1
        return SimpleNamespace(voices=self._voices)


class FakeClient:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.text_to_speech = FakeTTS()
        self.voices = FakeVoices(
            [
                SimpleNamespace(
                    voice_id="id-matilda",
                    name="Matilda - Professional",
                    category="premade",
                    labels={"use case": "narration", "accent": "american", "age": "middle_aged"},
                ),
                SimpleNamespace(
                    voice_id="id-river",
                    name="River",
                    category="premade",
                    labels=None,
                ),
            ]
        )


@pytest.fixture
def provider(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Provider with stub SDK client, real tmp-dir cache, playback disabled."""
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    from gensay.cache import TTSCache
    from gensay.providers import elevenlabs as el

    client = FakeClient()
    monkeypatch.setattr(el, "ElevenLabs", lambda api_key: client)
    monkeypatch.setattr(el, "play", lambda audio: None)

    cfg = TTSConfig(cache_enabled=True, extra={"api_key": "sk-test"})
    p = ElevenLabsProvider(cfg)
    p._cache = TTSCache(enabled=True, cache_dir=tmp_path / "cache")
    return SimpleNamespace(p=p, client=client)


def test_init_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(ValueError, match="API key not found"):
        ElevenLabsProvider(TTSConfig())


def test_init_env_key_beats_extra_key(monkeypatch: pytest.MonkeyPatch):
    from gensay.providers import elevenlabs as el

    seen: list[str] = []
    monkeypatch.setattr(el, "ElevenLabs", lambda api_key: seen.append(api_key))
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk-env")
    ElevenLabsProvider(TTSConfig(extra={"api_key": "sk-extra"}))
    assert seen == ["sk-env"]


def test_voice_name_resolves_to_id_case_insensitive(provider):
    p = provider.p
    assert p._resolve_voice_id("Matilda") == "id-matilda"  # short name before " - "
    assert p._resolve_voice_id("matilda - professional") == "id-matilda"
    assert p._resolve_voice_id("RIVER") == "id-river"


def test_voice_id_passthrough(provider):
    assert provider.p._resolve_voice_id("id-river") == "id-river"


def test_unknown_voice_raises(provider):
    with pytest.raises(ValueError, match="not found"):
        provider.p._resolve_voice_id("no-such-voice")


def test_list_voices_cached_once(provider):
    p = provider.p
    first = p.list_voices()
    second = p.list_voices()
    assert provider.client.voices.get_all_calls == 1
    assert len(first) == 2
    assert first[0]["use_case"] == "narration"
    assert second is first  # cached reference


def test_speak_uses_default_model_and_caches(provider):
    provider.p.speak("hello world", voice="Matilda")
    provider.p.speak("hello world", voice="Matilda")

    assert len(provider.client.text_to_speech.calls) == 1  # second call served from cache
    call = provider.client.text_to_speech.calls[0]
    assert call["voice_id"] == "id-matilda"
    assert call["text"] == "hello world"
    assert call["model_id"] == DEFAULT_MODEL


def test_different_models_get_separate_cache_entries(provider, tmp_path):
    """Same text/voice/format but different model → fresh synthesis (no stale reuse)."""
    provider.p.speak("shared text", voice="River")  # DEFAULT_MODEL
    assert len(provider.client.text_to_speech.calls) == 1

    p2 = ElevenLabsProvider(
        TTSConfig(cache_enabled=True, extra={"api_key": "k", "model": "eleven_v3"})
    )
    from gensay.cache import TTSCache

    p2._cache = TTSCache(enabled=True, cache_dir=tmp_path / "cache")  # shared cache dir
    p2.speak("shared text", voice="River")

    assert len(provider.client.text_to_speech.calls) == 2
    assert provider.client.text_to_speech.calls[1]["model_id"] == "eleven_v3"


def test_speak_chain_preserves_network_cause(provider):
    provider.client.text_to_speech.should_raise = ConnectionError("offline")
    with pytest.raises(RuntimeError, match="ElevenLabs TTS failed") as exc_info:
        provider.p.speak("hi", voice="Matilda")

    from gensay.fallback import is_network_error

    assert exc_info.value.__cause__ is not None
    assert is_network_error(exc_info.value)


def test_save_to_file_writes_bytes_and_format_map(provider, tmp_path):
    out = provider.p.save_to_file(
        "save me", tmp_path / "clip.wav", voice="River", format=AudioFormat.WAV
    )
    assert out.read_bytes() == FAKE_AUDIO
    call = provider.client.text_to_speech.calls[0]
    assert call["output_format"] == "pcm_24000"  # WAV maps to PCM, not mp3

    # No explicit format → config.format (defaults M4A); extension inference
    # happens in main(), not the provider
    provider.p.save_to_file("again", tmp_path / "clip.mp3", voice="River")
    assert provider.client.text_to_speech.calls[1]["output_format"] == "mp3_44100_128"


def test_save_to_file_cache_hit_skips_api(provider, tmp_path):
    out = tmp_path / "clip.mp3"
    provider.p.save_to_file("cache me", out, voice="River")
    provider.p.save_to_file("cache me", out, voice="River")
    assert len(provider.client.text_to_speech.calls) == 1


def test_model_override_via_extra(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    from gensay.cache import TTSCache
    from gensay.providers import elevenlabs as el

    client = FakeClient()
    monkeypatch.setattr(el, "ElevenLabs", lambda api_key: client)
    monkeypatch.setattr(el, "play", lambda audio: None)
    p = ElevenLabsProvider(
        TTSConfig(cache_enabled=False, extra={"api_key": "k", "model": "eleven_v3"})
    )
    p._cache = TTSCache(enabled=False, cache_dir=tmp_path / "c")

    p.save_to_file("hi", tmp_path / "o.mp3", voice="River")
    assert client.text_to_speech.calls[0]["model_id"] == "eleven_v3"


def test_rate_mapped_and_clamped_to_speed(provider):
    p = provider.p
    assert p._get_voice_settings(None).speed == 1.0
    assert p._get_voice_settings(150).speed == 1.0
    assert p._get_voice_settings(240).speed == 1.2  # clamped max
    assert p._get_voice_settings(60).speed == 0.7  # clamped min


def test_voice_settings_speed_rounding(provider):
    settings = provider.p._get_voice_settings(180)
    assert settings.speed == pytest.approx(1.2)
    assert settings.stability == 0.5
    assert settings.similarity_boost == 0.75
