"""Tests for offline network-error detection and macos fallback provider."""

from __future__ import annotations

import errno
import socket

import pytest

from gensay.fallback import NetworkFallbackProvider, is_network_error
from gensay.providers.base import TTSConfig


class TestIsNetworkError:
    def test_builtin_connection_errors(self):
        assert is_network_error(ConnectionError("refused"))
        assert is_network_error(ConnectionRefusedError("refused"))
        assert is_network_error(TimeoutError("timed out"))

    def test_dns_failure(self):
        assert is_network_error(socket.gaierror(8, "nodename nor servname provided"))

    def test_os_error_network_errno(self):
        assert is_network_error(OSError(errno.ENETUNREACH, "Network is unreachable"))
        assert is_network_error(OSError(errno.EHOSTUNREACH, "No route to host"))

    def test_non_network_errors(self):
        assert not is_network_error(ValueError("bad voice"))
        assert not is_network_error(RuntimeError("model exploded"))
        assert not is_network_error(OSError(errno.EPERM, "Operation not permitted"))

    def test_wrapped_chain(self):
        # providers wrap SDK errors: RuntimeError("TTS failed") from ConnectError
        try:
            try:
                raise ConnectionError("offline")
            except ConnectionError as e:
                raise RuntimeError("ElevenLabs TTS failed: offline") from e
        except RuntimeError as outer:
            assert is_network_error(outer)

    def test_sdk_exception_by_class_name(self):
        class EndpointConnectionError(Exception):
            pass

        class ConnectError(Exception):
            pass

        assert is_network_error(EndpointConnectionError("https://..."))
        assert is_network_error(ConnectError("[Errno 51] Network is unreachable"))

    def test_name_check_does_not_match_unrelated(self):
        class KeyboardLayoutError(Exception):
            pass

        assert not is_network_error(KeyboardLayoutError())


class StubProvider:
    """Minimal TTSProvider stand-in recording calls / raising on demand."""

    def __init__(self, config=None, raises: Exception | None = None):
        self.config = config or TTSConfig()
        self.raises = raises
        self.calls: list[tuple] = []

    def _maybe_raise(self, call: tuple):
        self.calls.append(call)
        if self.raises:
            raise self.raises

    def speak(self, text, voice=None, rate=None):
        self._maybe_raise(("speak", text, voice, rate))

    def save_to_file(self, text, output_path, voice=None, rate=None, format=None):
        self._maybe_raise(("save_to_file", text, str(output_path), voice, rate, format))
        from pathlib import Path

        return Path(output_path)

    def list_voices(self):
        return [{"id": "stub", "name": "Stub"}]

    def get_supported_formats(self):
        return []


def test_speak_falls_back_on_network_error():
    primary = StubProvider(raises=ConnectionError("offline"))
    fallback = StubProvider()
    proxy = NetworkFallbackProvider(primary, lambda: fallback, primary_name="elevenlabs")

    proxy.speak("hello", voice="Matilda", rate=180)

    assert primary.calls == [("speak", "hello", "Matilda", 180)]
    # fallback gets voice=None (cloud voice names invalid for `say`), rate passthrough
    assert fallback.calls == [("speak", "hello", None, 180)]


def test_save_to_file_falls_back_on_network_error(tmp_path):
    primary = StubProvider(raises=OSError(errno.ENETUNREACH, "unreachable"))
    fallback = StubProvider()
    proxy = NetworkFallbackProvider(primary, lambda: fallback)

    out = tmp_path / "out.m4a"
    result = proxy.save_to_file("hello", out, voice="Matilda")

    assert result == out
    assert fallback.calls[0][1] == "hello"
    assert fallback.calls[0][3] is None  # voice cleared


def test_non_network_error_does_not_fallback():
    primary = StubProvider(raises=ValueError("Voice 'Nope' not found"))
    fallback = StubProvider()
    proxy = NetworkFallbackProvider(primary, lambda: fallback)

    with pytest.raises(ValueError, match="not found"):
        proxy.speak("hello", voice="Nope")

    assert fallback.calls == []


def test_primary_success_never_touches_fallback():
    primary = StubProvider()
    fallback = StubProvider()
    proxy = NetworkFallbackProvider(primary, lambda: fallback)

    proxy.speak("hello", voice="Matilda")

    assert len(primary.calls) == 1
    assert fallback.calls == []


def test_fallback_constructed_lazily():
    factory_calls = []
    primary = StubProvider(raises=ConnectionError("offline"))
    proxy = NetworkFallbackProvider(
        primary,
        lambda: factory_calls.append(1) or StubProvider(),
    )

    proxy.speak("one")
    proxy.speak("one")  # cached

    assert len(factory_calls) == 1


def test_list_voices_uses_primary():
    primary = StubProvider()
    proxy = NetworkFallbackProvider(primary, lambda: StubProvider())
    assert proxy.list_voices() == [{"id": "stub", "name": "Stub"}]


def test_main_wraps_cloud_provider_with_macos_fallback(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys
):
    import sys

    from gensay import main as main_mod

    monkeypatch.setenv("GENSAY_CONFIG", str(tmp_path / "config.toml"))
    calls: list[tuple] = []

    class FlakyCloud:
        def __init__(self, config):
            self.config = config

        def speak(self, text, voice=None, rate=None):
            calls.append(("primary", text, voice))
            raise ConnectionError("offline")

        def save_to_file(self, text, output_path, voice=None, rate=None, format=None):
            raise ConnectionError("offline")

    class LocalSay:
        def __init__(self, config):
            calls.append(("macos_config_voice", config.voice))

        def speak(self, text, voice=None, rate=None):
            calls.append(("macos", text, voice))

        def save_to_file(self, text, output_path, voice=None, rate=None, format=None):
            from pathlib import Path

            return Path(output_path)

    stub_providers = dict(main_mod.get_providers())
    stub_providers["elevenlabs"] = FlakyCloud
    stub_providers["macos"] = LocalSay
    monkeypatch.setattr(main_mod, "get_providers", lambda: stub_providers)
    monkeypatch.setattr(sys, "argv", ["gensay", "-p", "elevenlabs", "hello offline"])

    main_mod.main()

    assert ("primary", "hello offline", None) in calls
    assert ("macos", "hello offline", None) in calls
    assert ("macos_config_voice", None) in calls  # voice-less config for `say`
    assert "falling back to macos" in capsys.readouterr().err


def test_wrapper_delegates_model_listing_and_display_metadata():
    class CloudishStub(StubProvider):
        display_name = "Acme"
        cache_namespace = "acme"

        def list_models(self):
            return [{"id": "m1", "current": True}]

    proxy = NetworkFallbackProvider(CloudishStub(), lambda: StubProvider())
    assert proxy.list_models() == [{"id": "m1", "current": True}]
    assert proxy.display_name == "Acme"
    assert proxy.cache_namespace == "acme"
