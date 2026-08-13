"""Tests for the chatterbox FFmpeg re-exec self-heal (macOS DYLD fix)."""

from __future__ import annotations

import sys

import pytest

from gensay.providers import chatterbox
from gensay.providers.chatterbox import reexec_with_ffmpeg_libs_if_needed


@pytest.fixture
def captured_exec(monkeypatch: pytest.MonkeyPatch):
    execs: list[tuple] = []
    monkeypatch.setattr(
        chatterbox.os, "execvpe", lambda path, argv, env: execs.append((path, argv, env))
    )
    monkeypatch.setattr(chatterbox.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        chatterbox, "_find_ffmpeg_lib_path", lambda: "/nix/store/abc-ffmpeg-7.1.1-lib/lib"
    )
    monkeypatch.delenv("DYLD_LIBRARY_PATH", raising=False)
    monkeypatch.delenv("GENSAY_FFMPEG_REEXEC", raising=False)
    monkeypatch.setattr(sys, "argv", ["gensay", "-p", "chatterbox", "hello"])
    return execs


def test_reexec_prepend_lib_path_and_guard(captured_exec):
    reexec_with_ffmpeg_libs_if_needed("chatterbox")

    path, argv, env = captured_exec[0]
    lib = "/nix/store/abc-ffmpeg-7.1.1-lib/lib"
    assert path == sys.executable
    assert argv == [sys.executable, "-m", "gensay", "-p", "chatterbox", "hello"]
    assert env["DYLD_LIBRARY_PATH"] == lib
    assert env["GENSAY_FFMPEG_REEXEC"] == "1"


def test_reexec_appends_to_existing_dyld(captured_exec, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DYLD_LIBRARY_PATH", "/other/lib")
    reexec_with_ffmpeg_libs_if_needed("chatterbox")

    env = captured_exec[0][2]
    assert env["DYLD_LIBRARY_PATH"] == "/nix/store/abc-ffmpeg-7.1.1-lib/lib:/other/lib"


def test_no_reexec_when_guard_set(captured_exec, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GENSAY_FFMPEG_REEXEC", "1")
    reexec_with_ffmpeg_libs_if_needed("chatterbox")
    assert captured_exec == []


def test_no_reexec_when_already_configured(captured_exec, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DYLD_LIBRARY_PATH", "/x:/nix/store/abc-ffmpeg-7.1.1-lib/lib:/y")
    reexec_with_ffmpeg_libs_if_needed("chatterbox")
    assert captured_exec == []


def test_no_reexec_without_ffmpeg(captured_exec, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chatterbox, "_find_ffmpeg_lib_path", lambda: None)
    reexec_with_ffmpeg_libs_if_needed("chatterbox")
    assert captured_exec == []


def test_no_reexec_on_linux(captured_exec, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chatterbox.platform, "system", lambda: "Linux")
    reexec_with_ffmpeg_libs_if_needed("chatterbox")
    assert captured_exec == []
