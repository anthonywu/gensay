"""Unit tests for DeepgramProvider with a stubbed httpx client (no network)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from gensay.providers import deepgram as dg
from gensay.providers.base import AudioFormat, TTSConfig
from gensay.providers.deepgram import DEFAULT_MODEL, DeepgramProvider

FAKE_MP3 = b"\xff\xfb" + b"x" * 128


class FakeResponse:
    def __init__(self, audio: bytes = FAKE_MP3):
        self.content = audio

    def raise_for_status(self):
        return None


class FakeClient:
    """Stands in for httpx.Client; records POSTs and returns fake audio."""

    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.calls: list[dict] = []
        self.should_raise: Exception | None = None

    def post(self, path, params=None, json=None):
        self.calls.append({"path": path, "params": params, "json": json})
        if self.should_raise:
            raise self.should_raise
        return FakeResponse()


def _make_provider(tmp_path, monkeypatch: pytest.MonkeyPatch, config: TTSConfig):
    """Build a provider with stub HTTP client, tmp-dir cache, afplay disabled."""
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    from gensay.cache import TTSCache

    client = FakeClient()
    plays: list[bytes] = []
    monkeypatch.setattr(dg.httpx, "Client", lambda **kwargs: client)
    monkeypatch.setattr(
        "gensay.providers.cloud.play_audio_bytes",
        lambda data, suffix=".mp3": plays.append(data),
    )

    p = DeepgramProvider(config)
    p._cache = TTSCache(enabled=True, cache_dir=tmp_path / "cache")
    return SimpleNamespace(p=p, client=client, plays=plays)


@pytest.fixture
def provider(tmp_path, monkeypatch: pytest.MonkeyPatch):
    return _make_provider(
        tmp_path, monkeypatch, TTSConfig(cache_enabled=True, extra={"api_key": "dg-test-key"})
    )


def test_init_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    with pytest.raises(ValueError, match="Deepgram API key not found"):
        DeepgramProvider(TTSConfig())


def test_api_key_env_precedence(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "env-key")
    monkeypatch.setattr(dg.httpx, "Client", lambda **kwargs: FakeClient(**kwargs))
    p = DeepgramProvider(TTSConfig(extra={"api_key": "extra-key"}))
    assert p._http.init_kwargs["headers"]["Authorization"] == "Token env-key"


def test_keychain_extra_key_used_when_env_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.setattr(dg.httpx, "Client", lambda **kwargs: FakeClient(**kwargs))
    p = DeepgramProvider(TTSConfig(extra={"api_key": "extra-key"}))
    assert p._http.init_kwargs["headers"]["Authorization"] == "Token extra-key"


def test_default_model_is_flux(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.setattr(dg.httpx, "Client", lambda **kwargs: FakeClient(**kwargs))
    p = DeepgramProvider(TTSConfig(extra={"api_key": "dg-test-key"}))
    assert p._default_model == DEFAULT_MODEL
    assert DEFAULT_MODEL.startswith("flux-")


def test_speak_flux_routes_to_v2(provider):
    provider.p.speak("hello flux")
    assert len(provider.client.calls) == 1
    call = provider.client.calls[0]
    assert call["path"] == "/v2/speak"
    assert call["params"]["model"] == DEFAULT_MODEL
    assert call["params"]["encoding"] == "mp3"
    assert "speed" not in call["params"]
    assert call["json"] == {"text": "hello flux"}
    assert len(provider.plays) == 1


def test_speak_short_name_resolves_flux_voice(provider):
    provider.p.speak("hi kit", voice="kit")
    assert provider.client.calls[0]["path"] == "/v2/speak"
    assert provider.client.calls[0]["params"]["model"] == "flux-kit-en"


def test_speak_aura2_short_name_routes_to_v1(provider):
    provider.p.speak("hi thalia", voice="thalia")
    call = provider.client.calls[0]
    assert call["path"] == "/v1/speak"
    assert call["params"]["model"] == "aura-2-thalia-en"


def test_aura2_non_english_short_name(provider):
    provider.p.speak("hola", voice="celeste")
    call = provider.client.calls[0]
    assert call["path"] == "/v1/speak"
    assert call["params"]["model"] == "aura-2-celeste-es"


def test_full_model_string_passthrough(provider):
    provider.p.speak("hi", voice="aura-helios-en")
    call = provider.client.calls[0]
    assert call["path"] == "/v1/speak"
    assert call["params"]["model"] == "aura-helios-en"


def test_unknown_voice_raises(provider):
    with pytest.raises(ValueError, match="not found"):
        provider.p.speak("hi", voice="no-such-voice")
    assert provider.client.calls == []


def test_speed_snapped_for_flux(provider):
    provider.p.speak("fast talk", rate=180)  # 180/150=1.2 → clamp+snap to 1.15
    assert provider.client.calls[0]["params"]["speed"] == 1.15


def test_speed_within_flux_range(provider):
    provider.p.speak("slightly faster", rate=165)  # 1.1 exactly
    assert provider.client.calls[0]["params"]["speed"] == 1.1


def test_speed_slow_snapped_for_flux(provider):
    provider.p.speak("slow", rate=105)  # 0.7 → clamp to 0.85
    assert provider.client.calls[0]["params"]["speed"] == 0.85


def test_speed_continuous_for_aura(provider):
    provider.p.speak("aur2", voice="aura-2-asteria-en", rate=225)  # 1.5
    call = provider.client.calls[0]
    assert call["params"]["speed"] == 1.5
    assert call["path"] == "/v1/speak"


def test_speed_clamped_for_aura(provider):
    provider.p.speak("aura fast", voice="aura-2-asteria-en", rate=600)  # 4.0 → 2.0
    assert provider.client.calls[0]["params"]["speed"] == 2.0


def test_save_to_file_wav(provider, tmp_path):
    out = tmp_path / "clip.wav"
    result = provider.p.save_to_file("save me", out, voice="haley", format=AudioFormat.WAV)
    assert result == out
    assert out.read_bytes() == FAKE_MP3
    call = provider.client.calls[0]
    assert call["params"]["encoding"] == "linear16"
    assert call["params"]["container"] == "wav"


def test_save_to_file_ogg_uses_opus(provider, tmp_path):
    out = tmp_path / "clip.ogg"
    provider.p.save_to_file("save me", out, format=AudioFormat.OGG)
    call = provider.client.calls[0]
    assert call["params"]["encoding"] == "opus"
    assert call["params"]["container"] == "ogg"


def test_cache_hit_skips_http(provider, tmp_path):
    out = tmp_path / "clip.mp3"
    provider.p.save_to_file("cached", out)
    provider.p.save_to_file("cached", out)
    assert len(provider.client.calls) == 1
    assert out.read_bytes() == FAKE_MP3


def test_speak_cache_hit_still_plays(provider):
    provider.p.speak("same text twice")
    provider.p.speak("same text twice")
    assert len(provider.client.calls) == 1
    assert len(provider.plays) == 2


def test_save_to_file_error_wrapped(provider, tmp_path):
    provider.client.should_raise = RuntimeError("boom-500")
    with pytest.raises(RuntimeError, match="Deepgram TTS failed: boom-500"):
        provider.p.save_to_file("x", tmp_path / "x.mp3")


def test_registered_in_main():
    """Registration guard: provider is wired into the CLI surface."""
    from gensay.main import CLOUD_PROVIDERS, PROVIDER_NAMES, get_providers

    assert "deepgram" in PROVIDER_NAMES
    assert "deepgram" in CLOUD_PROVIDERS  # gets offline fallback to macos `say`
    assert get_providers()["deepgram"] is DeepgramProvider


def test_http_error_wrapped(provider):
    provider.client.should_raise = RuntimeError("boom-401")
    with pytest.raises(RuntimeError, match="Deepgram TTS failed: boom-401"):
        provider.p.speak("hello")
    assert provider.plays == []


def test_extra_model_default(tmp_path, monkeypatch: pytest.MonkeyPatch):
    ns = _make_provider(
        tmp_path,
        monkeypatch,
        TTSConfig(extra={"api_key": "dg-test-key", "model": "aura-2-thalia-en"}),
    )
    ns.p.speak("default model from config")
    assert ns.client.calls[0]["params"]["model"] == "aura-2-thalia-en"


def test_invalid_model_rejected_at_construction(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """A non-Deepgram model string (e.g. an ElevenLabs id) fails fast, not silently."""
    with pytest.raises(ValueError, match="Invalid Deepgram model 'eleven_v3'"):
        _make_provider(
            tmp_path,
            monkeypatch,
            TTSConfig(extra={"api_key": "dg-test-key", "model": "eleven_v3"}),
        )


def test_config_voice_used_when_no_flag(tmp_path, monkeypatch: pytest.MonkeyPatch):
    ns = _make_provider(
        tmp_path, monkeypatch, TTSConfig(voice="Miles", extra={"api_key": "dg-test-key"})
    )
    ns.p.speak("from config voice")
    assert ns.client.calls[0]["params"]["model"] == "flux-miles-en"


def test_list_voices_static(provider):
    voices = provider.p.list_voices()
    ids = {v["id"] for v in voices}
    assert DEFAULT_MODEL in ids
    assert "aura-2-thalia-en" in ids
    assert "aura-asteria-en" in ids
    assert all("id" in v and "name" in v and "language" in v and "family" in v for v in voices)


def test_list_voices_returns_copy(provider):
    voices = provider.p.list_voices()
    voices.clear()
    assert len(provider.p.list_voices()) > 0


def test_supported_formats(provider):
    formats = provider.p.get_supported_formats()
    assert AudioFormat.MP3 in formats
    assert AudioFormat.WAV in formats
    assert AudioFormat.FLAC in formats


def test_playback_temp_file_cleaned_up(monkeypatch):
    """Shared playback writes a temp file for afplay and always cleans it up."""
    from gensay.providers import playback

    played_paths: list[Path] = []

    def fake_run(cmd, check):
        played_paths.append(Path(cmd[1]))

    monkeypatch.setattr(playback.subprocess, "run", fake_run)
    monkeypatch.setattr(playback.sys, "platform", "darwin")
    playback.play_audio_bytes(FAKE_MP3, ".mp3")
    assert played_paths, "afplay should have been invoked"
    assert not played_paths[0].exists()
