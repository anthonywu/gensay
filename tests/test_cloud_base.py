"""Tests for the shared CloudTTSProvider pipeline (providers/cloud.py)."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from gensay.cache import TTSCache
from gensay.providers import playback
from gensay.providers.base import AudioFormat, TTSConfig
from gensay.providers.cloud import CloudTTSProvider, PreparedSynthesis

FAKE_AUDIO = b"\xff\xfbfake-audio"


class FakeCloudProvider(CloudTTSProvider):
    """Minimal concrete provider: records synth calls, no network."""

    cache_namespace = "fakecloud"
    display_name = "FakeCloud"

    def __init__(self, config: TTSConfig | None = None):
        super().__init__(config)
        self.synth_calls: list[dict[str, Any]] = []
        self.fail_synthesis: Exception | None = None

    def _prepare(self, text, voice, rate, format):
        voice = voice or self.config.voice or "default-voice"
        if voice == "bogus":
            raise ValueError(f"Voice '{voice}' not found.")
        fmt = (format or AudioFormat.MP3).value

        def synthesize() -> bytes:
            if self.fail_synthesis:
                raise self.fail_synthesis
            self.synth_calls.append({"text": text, "voice": voice, "format": fmt})
            return FAKE_AUDIO

        return PreparedSynthesis(cache_parts=(text, voice, rate, fmt), synthesize=synthesize)

    def list_voices(self):
        return [{"id": "default-voice", "name": "Default"}]

    def get_supported_formats(self):
        return [AudioFormat.MP3]


@pytest.fixture
def provider(tmp_path, monkeypatch):
    plays: list[bytes] = []
    monkeypatch.setattr(
        playback, "play_audio_bytes", lambda data, suffix=".mp3": plays.append(data)
    )
    p = FakeCloudProvider(TTSConfig(cache_enabled=True))
    p._cache = TTSCache(enabled=True, cache_dir=tmp_path / "cache")
    p.plays = plays  # type: ignore[attr-defined]
    return p


class TestSpeakPipeline:
    def test_speak_synthesizes_and_plays(self, provider, monkeypatch):
        played: list[tuple[bytes, str]] = []
        monkeypatch.setattr(
            "gensay.providers.playback.play_audio_bytes",
            lambda data, suffix: played.append((data, suffix)),
        )
        provider.speak("hello")
        assert provider.synth_calls == [
            {"text": "hello", "voice": "default-voice", "format": "mp3"}
        ]
        assert played == [(FAKE_AUDIO, ".mp3")]

    def test_speak_uses_cache_on_second_call(self, provider, monkeypatch):
        monkeypatch.setattr("gensay.providers.playback.play_audio_bytes", lambda *a: None)
        provider.speak("hello")
        provider.speak("hello")
        assert len(provider.synth_calls) == 1

    def test_speak_wraps_synthesis_errors(self, provider):
        provider.fail_synthesis = ConnectionError("dns down")
        with pytest.raises(RuntimeError, match="FakeCloud TTS failed: dns down") as exc_info:
            provider.speak("hello")
        # Cause chain preserved for offline-fallback network detection
        assert isinstance(exc_info.value.__cause__, ConnectionError)

    def test_speak_bad_voice_raises_unwrapped_valueerror(self, provider):
        with pytest.raises(ValueError, match="Voice 'bogus' not found"):
            provider.speak("hello", voice="bogus")


class StreamingFakeCloudProvider(FakeCloudProvider):
    """Fake provider that also offers chunked synthesis."""

    CHUNKS = (b"\xff\xfb", b"chunk-one", b"chunk-two")

    def _prepare(self, text, voice, rate, format):
        prepared = super()._prepare(text, voice, rate, format)

        def synthesize_stream():
            if self.fail_synthesis:
                raise self.fail_synthesis
            self.synth_calls.append({"text": text, "streamed": True})
            yield from self.CHUNKS

        return PreparedSynthesis(
            cache_parts=prepared.cache_parts,
            synthesize=prepared.synthesize,
            synthesize_stream=synthesize_stream,
        )


@pytest.fixture
def stream_provider(tmp_path, monkeypatch):
    """Streaming-capable provider with a fake stdin player installed."""
    streams: list[bytes] = []

    def fake_stream_audio_bytes(chunks, suffix=".mp3"):
        data = b"".join(chunks)
        streams.append(data)
        return data

    monkeypatch.setattr(playback, "find_stream_player", lambda: ["/fake/ffplay"])
    monkeypatch.setattr(playback, "stream_audio_bytes", fake_stream_audio_bytes)
    plays: list[bytes] = []
    monkeypatch.setattr(
        playback, "play_audio_bytes", lambda data, suffix=".mp3": plays.append(data)
    )
    p = StreamingFakeCloudProvider(TTSConfig(cache_enabled=True))
    p._cache = TTSCache(enabled=True, cache_dir=tmp_path / "cache")
    p.streams = streams  # type: ignore[attr-defined]
    p.plays = plays  # type: ignore[attr-defined]
    return p


class TestStreamingSpeak:
    FULL_AUDIO = b"".join(StreamingFakeCloudProvider.CHUNKS)

    def test_cache_miss_streams_and_caches(self, stream_provider):
        stream_provider.speak("hello")
        assert stream_provider.streams == [self.FULL_AUDIO]
        assert stream_provider.plays == []
        # Second call is a cache hit: plays buffered bytes, no new stream
        stream_provider.speak("hello")
        assert stream_provider.streams == [self.FULL_AUDIO]
        assert stream_provider.plays == [self.FULL_AUDIO]

    def test_stream_disabled_uses_buffered_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(playback, "find_stream_player", lambda: ["/fake/ffplay"])
        plays: list[bytes] = []
        monkeypatch.setattr(playback, "play_audio_bytes", lambda data, suffix: plays.append(data))
        p = StreamingFakeCloudProvider(TTSConfig(cache_enabled=True, stream_enabled=False))
        p._cache = TTSCache(enabled=True, cache_dir=tmp_path / "cache")
        p.speak("hello")
        assert plays == [FAKE_AUDIO]  # buffered synthesize(), not the stream

    def test_no_player_falls_back_to_buffered(self, stream_provider, monkeypatch):
        monkeypatch.setattr(playback, "find_stream_player", lambda: None)
        stream_provider.speak("hello")
        assert stream_provider.streams == []
        assert stream_provider.plays == [FAKE_AUDIO]

    def test_stream_failure_wraps_and_does_not_cache(self, stream_provider):
        stream_provider.fail_synthesis = ConnectionError("dns down")
        with pytest.raises(RuntimeError, match="FakeCloud TTS failed: dns down"):
            stream_provider.speak("hello")
        stream_provider.fail_synthesis = None
        stream_provider.speak("hello")  # miss again: nothing was cached
        assert stream_provider.streams == [self.FULL_AUDIO]

    def test_save_to_file_stays_buffered(self, stream_provider, tmp_path):
        out = stream_provider.save_to_file("hello", tmp_path / "out.mp3")
        assert out.read_bytes() == FAKE_AUDIO
        assert stream_provider.streams == []


class TestSaveToFile:
    def test_save_writes_audio(self, provider, tmp_path):
        out = provider.save_to_file("hello", tmp_path / "out.mp3")
        assert out.read_bytes() == FAKE_AUDIO

    def test_save_uses_cache(self, provider, tmp_path):
        provider.save_to_file("hello", tmp_path / "a.mp3")
        provider.save_to_file("hello", tmp_path / "b.mp3")
        assert len(provider.synth_calls) == 1
        assert (tmp_path / "b.mp3").read_bytes() == FAKE_AUDIO

    def test_save_wraps_errors(self, provider, tmp_path):
        provider.fail_synthesis = ConnectionError("offline")
        with pytest.raises(RuntimeError, match="FakeCloud TTS failed: offline"):
            provider.save_to_file("hello", tmp_path / "out.mp3")

    def test_format_resolution_prefers_explicit_arg(self, provider, tmp_path):
        provider.save_to_file("hello", tmp_path / "out.mp3", format=AudioFormat.MP3)
        assert provider.synth_calls[0]["format"] == "mp3"


class TestCacheKey:
    def test_matches_fstring_layout(self, provider):
        # Key must be sha256("namespace|part|part|...") with f-string
        # stringification, so migrated providers keep their cache entries.
        key = provider._cache_key("text", "voice", 1.0, None, "mp3")
        expected = hashlib.sha256(b"fakecloud|text|voice|1.0|None|mp3").hexdigest()
        assert key == expected

    def test_speak_and_save_share_cache_for_same_parts(self, provider, tmp_path, monkeypatch):
        monkeypatch.setattr("gensay.providers.playback.play_audio_bytes", lambda *a: None)
        provider.speak("hello")
        provider.save_to_file("hello", tmp_path / "out.mp3", format=AudioFormat.MP3)
        assert len(provider.synth_calls) == 1


class TestProgress:
    def test_progress_milestones_on_miss_then_hit(self, tmp_path, monkeypatch):
        events: list[tuple[float, str]] = []
        p = FakeCloudProvider(
            TTSConfig(
                cache_enabled=True, progress_callback=lambda pct, msg: events.append((pct, msg))
            )
        )
        p._cache = TTSCache(enabled=True, cache_dir=tmp_path / "cache")
        monkeypatch.setattr("gensay.providers.playback.play_audio_bytes", lambda *a: None)

        p.speak("hello")
        assert [pct for pct, _ in events] == [0.0, 0.2, 0.8, 1.0]

        events.clear()
        p.speak("hello")
        assert [pct for pct, _ in events] == [0.0, 0.5, 0.8, 1.0]


class TestResolveApiKey:
    def test_env_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("FAKE_API_KEY", "env-key")
        key = CloudTTSProvider.resolve_api_key(
            "FAKE_API_KEY", TTSConfig(extra={"api_key": "extra-key"}), display_name="Fake"
        )
        assert key == "env-key"

    def test_config_extra_fallback(self, monkeypatch):
        monkeypatch.delenv("FAKE_API_KEY", raising=False)
        key = CloudTTSProvider.resolve_api_key(
            "FAKE_API_KEY", TTSConfig(extra={"api_key": "extra-key"}), display_name="Fake"
        )
        assert key == "extra-key"

    def test_missing_key_raises_with_hint(self, monkeypatch):
        monkeypatch.delenv("FAKE_API_KEY", raising=False)
        with pytest.raises(ValueError, match="Fake API key not found.*FAKE_API_KEY"):
            CloudTTSProvider.resolve_api_key("FAKE_API_KEY", TTSConfig(), display_name="Fake")

    def test_hint_appended(self, monkeypatch):
        monkeypatch.delenv("FAKE_API_KEY", raising=False)
        with pytest.raises(ValueError, match="gensay config set fake.api_key"):
            CloudTTSProvider.resolve_api_key(
                "FAKE_API_KEY",
                TTSConfig(),
                display_name="Fake",
                config_hint="(e.g. via `gensay config set fake.api_key`)",
            )
