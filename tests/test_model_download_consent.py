"""Tests for the first-download consent prompt (chatterbox, ~4 GB)."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from gensay.providers import chatterbox
from gensay.providers.chatterbox import (
    MODEL_REPO_ID,
    ModelDownloadDeclinedError,
    _confirm_model_download,
)


@pytest.fixture
def uncached(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chatterbox, "_model_cached", lambda repo_id: False)


@pytest.fixture
def tty_stdin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True, fileno=lambda: 0))


def test_cached_model_skips_prompt(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chatterbox, "_model_cached", lambda repo_id: True)
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("input() should not be called"))
    _confirm_model_download()  # no exception, no prompt


def test_tty_empty_answer_defaults_yes(uncached, tty_stdin, monkeypatch: pytest.MonkeyPatch):
    answers = iter([""])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    _confirm_model_download()  # empty → Yes


def test_tty_explicit_yes(uncached, tty_stdin, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("builtins.input", lambda *a: "y")
    _confirm_model_download()


def test_tty_no_declines_without_downloading(uncached, tty_stdin, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("builtins.input", lambda *a: "n")
    with pytest.raises(ModelDownloadDeclinedError, match="declined"):
        _confirm_model_download()


def test_prompt_mentions_repo_and_size(uncached, tty_stdin, monkeypatch: pytest.MonkeyPatch):
    prompts: list[str] = []
    monkeypatch.setattr("builtins.input", lambda msg="": prompts.append(msg) or "")
    _confirm_model_download()
    assert MODEL_REPO_ID in prompts[0]
    assert "GB" in prompts[0]
    assert "[Y/n]" in prompts[0]


def test_non_tty_proceeds_with_stderr_note(uncached, monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: False))

    def no_input(*a):
        pytest.fail("input() must not be called without a TTY")

    monkeypatch.setattr("builtins.input", no_input)
    _confirm_model_download()
    err = capsys.readouterr().err
    assert "non-interactive" in err


def test_load_model_prompts_before_downloading(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Declining must abort _load_model before any model load happens."""
    from types import ModuleType

    from gensay.providers.base import TTSConfig
    from gensay.providers.chatterbox import ChatterboxProvider

    monkeypatch.setattr(chatterbox, "_check_ffmpeg_libs", lambda: None)
    monkeypatch.setattr(
        chatterbox,
        "_confirm_model_download",
        lambda: (_ for _ in ()).throw(ModelDownloadDeclinedError("declined")),
    )

    # Make heavy imports resolvable in matrix envs (no torch/chatterbox installed)
    fake_ta = ModuleType("torchaudio")
    fake_turbo = ModuleType("chatterbox.tts_turbo")
    fake_turbo.ChatterboxTurboTTS = SimpleNamespace()
    fake_pkg = ModuleType("chatterbox")
    fake_pkg.tts_turbo = fake_turbo
    monkeypatch.setitem(sys.modules, "torchaudio", fake_ta)
    monkeypatch.setitem(sys.modules, "chatterbox", fake_pkg)
    monkeypatch.setitem(sys.modules, "chatterbox.tts_turbo", fake_turbo)

    p = ChatterboxProvider(TTSConfig(cache_enabled=False))
    with pytest.raises(ModelDownloadDeclinedError):
        p.warmup()
    assert p._model_loaded is False


def test_model_cached_reporting(monkeypatch: pytest.MonkeyPatch):
    """_model_cached defers to HF local probe (no network)."""
    import sys as _sys
    from types import ModuleType

    calls: list = []
    fake_hub = ModuleType("huggingface_hub")
    fake_hub.snapshot_download = lambda repo_id, local_files_only: calls.append(repo_id)
    monkeypatch.setitem(_sys.modules, "huggingface_hub", fake_hub)

    from gensay.providers.chatterbox import _model_cached

    assert _model_cached("some/repo") is True
    assert calls == ["some/repo"]

    def boom(repo_id, local_files_only):
        raise OSError("offline")

    fake_hub.snapshot_download = boom
    assert _model_cached("some/repo") is False
