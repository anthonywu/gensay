"""Unit tests for GeminiProvider with a stubbed httpx client (no network)."""

from __future__ import annotations

import base64
import io
import wave
from types import SimpleNamespace

import pytest

from gensay.providers import gemini as gm
from gensay.providers.base import AudioFormat, TTSConfig
from gensay.providers.gemini import DEFAULT_MODEL, DEFAULT_VOICE, GeminiProvider

FAKE_PCM = b"\x00\x01" * 256  # 16-bit mono samples


def _response_payload(pcm: bytes = FAKE_PCM, rate: int = 24000) -> dict:
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": f"audio/L16;codec=pcm;rate={rate}",
                                "data": base64.b64encode(pcm).decode(),
                            }
                        }
                    ]
                }
            }
        ]
    }


class FakeResponse:
    def __init__(self, payload: dict | None = None, status_code: int = 200):
        self._payload = payload if payload is not None else _response_payload()
        self.status_code = status_code
        self.request = SimpleNamespace()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeClient:
    """Stands in for httpx.Client; records POSTs and returns fake audio."""

    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.calls: list[dict] = []
        self.responses: list[FakeResponse] = []

    def post(self, path, json=None):
        self.calls.append({"path": path, "json": json})
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse()


def _make_provider(tmp_path, monkeypatch: pytest.MonkeyPatch, config: TTSConfig):
    """Build a provider with stub HTTP client, tmp-dir cache, playback stubbed."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    from gensay.cache import TTSCache

    client = FakeClient()
    plays: list[bytes] = []
    monkeypatch.setattr(gm.httpx, "Client", lambda **kwargs: client)
    monkeypatch.setattr(
        "gensay.providers.playback.play_audio_bytes",
        lambda data, suffix=".wav": plays.append(data),
    )
    monkeypatch.setattr("gensay.providers.playback.find_stream_player", lambda: None)

    p = GeminiProvider(config)
    p._cache = TTSCache(enabled=True, cache_dir=tmp_path / "cache")
    return SimpleNamespace(p=p, client=client, plays=plays)


@pytest.fixture
def provider(tmp_path, monkeypatch: pytest.MonkeyPatch):
    return _make_provider(
        tmp_path, monkeypatch, TTSConfig(cache_enabled=True, extra={"api_key": "gm-test-key"})
    )


def test_init_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="Gemini API key not found"):
        GeminiProvider(TTSConfig())


def test_api_key_env_precedence(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    monkeypatch.setattr(gm.httpx, "Client", lambda **kwargs: FakeClient(**kwargs))
    p = GeminiProvider(TTSConfig(extra={"api_key": "extra-key"}))
    assert p._http.init_kwargs["headers"]["x-goog-api-key"] == "env-key"


def test_google_api_key_fallback(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    monkeypatch.setattr(gm.httpx, "Client", lambda **kwargs: FakeClient(**kwargs))
    p = GeminiProvider(TTSConfig())
    assert p._http.init_kwargs["headers"]["x-goog-api-key"] == "google-key"


def test_keychain_extra_key_used_when_env_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(gm.httpx, "Client", lambda **kwargs: FakeClient(**kwargs))
    p = GeminiProvider(TTSConfig(extra={"api_key": "extra-key"}))
    assert p._http.init_kwargs["headers"]["x-goog-api-key"] == "extra-key"


def test_invalid_model_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(gm.httpx, "Client", lambda **kwargs: FakeClient(**kwargs))
    with pytest.raises(ValueError, match="Invalid Gemini model"):
        GeminiProvider(TTSConfig(extra={"api_key": "k", "model": "tts-1"}))


def test_speak_posts_generate_content(provider):
    provider.p.speak("hello gemini")
    assert len(provider.client.calls) == 1
    call = provider.client.calls[0]
    assert call["path"] == f"/v1beta/models/{DEFAULT_MODEL}:generateContent"
    body = call["json"]
    assert body["contents"] == [{"parts": [{"text": "hello gemini"}]}]
    gen = body["generationConfig"]
    assert gen["responseModalities"] == ["AUDIO"]
    voice = gen["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"]
    assert voice == DEFAULT_VOICE
    assert len(provider.plays) == 1


def test_multi_speaker_voice_spec(provider):
    provider.p.speak("Joe: hi there\nJane: hello!", voice="Joe=Kore,Jane=puck")
    gen = provider.client.calls[0]["json"]["generationConfig"]
    configs = gen["speechConfig"]["multiSpeakerVoiceConfig"]["speakerVoiceConfigs"]
    assert configs == [
        {"speaker": "Joe", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}},
        {"speaker": "Jane", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Puck"}}},
    ]
    assert len(provider.plays) == 1


def test_multi_speaker_rejects_more_than_two(provider):
    with pytest.raises(ValueError, match="at most 2 speakers"):
        provider.p.speak("x", voice="A=Kore,B=Puck,C=Leda")


def test_multi_speaker_rejects_malformed_spec(provider):
    with pytest.raises(ValueError, match="Invalid multi-speaker spec"):
        provider.p.speak("x", voice="Joe=")
    with pytest.raises(ValueError, match="not found"):
        provider.p.speak("x", voice="Joe=NotAVoice")


def test_playback_audio_is_wav_wrapped_pcm(provider):
    provider.p.speak("wrap me")
    with wave.open(io.BytesIO(provider.plays[0]), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 24000
        assert wf.readframes(wf.getnframes()) == FAKE_PCM


def test_sample_rate_parsed_from_mime_type(provider):
    provider.client.responses.append(FakeResponse(_response_payload(rate=16000)))
    provider.p.speak("rate check")
    with wave.open(io.BytesIO(provider.plays[0]), "rb") as wf:
        assert wf.getframerate() == 16000


def test_voice_resolution_case_insensitive(provider):
    provider.p.speak("hi", voice="puck")
    voice = provider.client.calls[0]["json"]["generationConfig"]["speechConfig"]["voiceConfig"][
        "prebuiltVoiceConfig"
    ]["voiceName"]
    assert voice == "Puck"


def test_unknown_voice_raises(provider):
    with pytest.raises(ValueError, match="Voice 'nope' not found"):
        provider.p.speak("hi", voice="nope")
    assert provider.client.calls == []


def test_rate_becomes_pace_instruction(provider):
    provider.p.speak("hurry", rate=180)
    text = provider.client.calls[0]["json"]["contents"][0]["parts"][0]["text"]
    assert text == "[speak at roughly 180 words per minute]\n\nhurry"


def test_style_prompt_prepended(tmp_path, monkeypatch: pytest.MonkeyPatch):
    ctx = _make_provider(
        tmp_path,
        monkeypatch,
        TTSConfig(extra={"api_key": "k", "prompt": "Say cheerfully:"}),
    )
    ctx.p.speak("good news")
    text = ctx.client.calls[0]["json"]["contents"][0]["parts"][0]["text"]
    assert text == "Say cheerfully:\n\ngood news"


def test_speak_uses_cache_on_second_call(provider):
    provider.p.speak("cache me")
    provider.p.speak("cache me")
    assert len(provider.client.calls) == 1
    assert len(provider.plays) == 2


def test_cache_key_varies_with_voice(provider, tmp_path):
    provider.p.speak("text")
    provider.p.speak("text", voice="Leda")
    assert len(provider.client.calls) == 2
    # Playback and WAV save share cache parts (both wav) → cache hit, no call.
    provider.p.save_to_file("text", tmp_path / "out.wav", format=AudioFormat.WAV)
    assert len(provider.client.calls) == 2


def test_save_to_file_wav(provider, tmp_path):
    out = provider.p.save_to_file("to disk", tmp_path / "speech.wav", format=AudioFormat.WAV)
    with wave.open(str(out), "rb") as wf:
        assert wf.readframes(wf.getnframes()) == FAKE_PCM


def test_retry_on_5xx_then_success(provider):
    provider.client.responses.append(FakeResponse(status_code=500))
    provider.client.responses.append(FakeResponse())
    provider.p.speak("flaky")
    assert len(provider.client.calls) == 2
    assert len(provider.plays) == 1


def test_retry_on_audioless_response_then_success(provider):
    provider.client.responses.append(FakeResponse({"candidates": [{"content": {"parts": []}}]}))
    provider.client.responses.append(FakeResponse())
    provider.p.speak("textish")
    assert len(provider.client.calls) == 2


def test_fails_after_two_audioless_responses(provider):
    provider.client.responses.append(FakeResponse(status_code=500))
    provider.client.responses.append(FakeResponse(status_code=500))
    with pytest.raises(RuntimeError, match="Gemini TTS failed"):
        provider.p.speak("never works")
    assert len(provider.client.calls) == 2


def test_4xx_surfaces_api_error_message(provider):
    provider.client.responses.append(
        FakeResponse(
            {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key."}},
            status_code=400,
        )
    )
    with pytest.raises(RuntimeError) as exc:
        provider.p.speak("bad key")
    msg = str(exc.value)
    assert "API key not valid" in msg
    # key-related errors explain which credential was used and env precedence
    assert "configured gemini.api_key" in msg
    assert "environment variables take precedence" in msg
    assert len(provider.client.calls) == 1  # 4xx is not retried


def test_4xx_non_key_error_has_no_credential_hint(provider):
    provider.client.responses.append(
        FakeResponse(
            {"error": {"code": 400, "message": "Invalid value at 'generation_config'."}},
            status_code=400,
        )
    )
    with pytest.raises(RuntimeError) as exc:
        provider.p.speak("bad config")
    msg = str(exc.value)
    assert "Invalid value at 'generation_config'" in msg
    assert "credential used" not in msg


def test_list_voices_catalog(provider):
    voices = provider.p.list_voices()
    assert len(voices) == 30
    assert {"id": "Kore", "name": "Kore", "description": "Firm"} in voices


def test_list_models_marks_current(provider):
    models = provider.p.list_models()
    assert [m["id"] for m in models if m["current"]] == [DEFAULT_MODEL]


def test_list_models_declares_capabilities(provider):
    models = {m["id"]: m["capabilities"] for m in provider.p.list_models()}
    for caps in models.values():
        assert "multi-speaker" in caps
        assert "prompt-steerable" in caps
    # streaming is a 3.1-preview-only capability
    assert "streaming" in models["gemini-3.1-flash-tts-preview"]
    assert "streaming" not in models[DEFAULT_MODEL]


def test_supported_formats(provider):
    formats = provider.p.get_supported_formats()
    assert AudioFormat.WAV in formats
    assert AudioFormat.MP3 in formats
    assert AudioFormat.M4A in formats
