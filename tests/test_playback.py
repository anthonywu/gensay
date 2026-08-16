"""Tests for playback helpers (streaming player discovery and piping)."""

from __future__ import annotations

import shutil

import pytest

from gensay.providers import playback


class TestFindStreamPlayer:
    def test_prefers_ffplay(self, monkeypatch):
        monkeypatch.setattr(playback.shutil, "which", lambda name: f"/usr/bin/{name}")
        argv = playback.find_stream_player()
        assert argv is not None
        assert argv[0] == "/usr/bin/ffplay"

    def test_falls_back_to_mpv(self, monkeypatch):
        monkeypatch.setattr(
            playback.shutil,
            "which",
            lambda name: "/usr/bin/mpv" if name == "mpv" else None,
        )
        argv = playback.find_stream_player()
        assert argv is not None
        assert argv[0] == "/usr/bin/mpv"
        assert argv[-1] == "-"

    def test_none_when_no_player(self, monkeypatch):
        monkeypatch.setattr(playback.shutil, "which", lambda name: None)
        assert playback.find_stream_player() is None


class TestStreamAudioBytes:
    def test_raises_without_player(self, monkeypatch):
        monkeypatch.setattr(playback, "find_stream_player", lambda: None)
        with pytest.raises(RuntimeError, match="no streaming audio player"):
            playback.stream_audio_bytes([b"x"])

    def test_pipes_chunks_and_returns_accumulated_bytes(self, monkeypatch):
        # A stdin sink stands in for a real player: consumes stdin, exits 0.
        cat = shutil.which("cat")
        assert cat, "cat required for this test"
        monkeypatch.setattr(playback, "find_stream_player", lambda: [cat])
        chunks = [b"one", b"", b"two", b"three"]
        assert playback.stream_audio_bytes(iter(chunks)) == b"onetwothree"

    def test_player_failure_raises(self, monkeypatch):
        # `false` exits 1 immediately without reading stdin: either the
        # nonzero exit or the broken pipe must surface as RuntimeError.
        false = shutil.which("false")
        assert false, "false required for this test"
        monkeypatch.setattr(playback, "find_stream_player", lambda: [false])
        with pytest.raises(RuntimeError, match="stream player"):
            playback.stream_audio_bytes([b"x" * 1024 * 1024] * 64)
