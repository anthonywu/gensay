"""Tests: config-file voice defaults don't leak across providers."""

from __future__ import annotations

import pytest

from gensay.main import _apply_voice_provider_scope, _voice_flag_explicit
from gensay.user_config import UserConfig


def _args(provider="polly", voice="Matilda"):
    from argparse import Namespace

    return Namespace(provider=provider, voice=voice)


@pytest.fixture
def el_cfg():
    return UserConfig(provider="elevenlabs", voice="Matilda")


def test_config_voice_dropped_on_other_provider(el_cfg, capsys):
    args = _args(provider="polly", voice="Matilda")
    _apply_voice_provider_scope(args, el_cfg, ["hello"])
    assert args.voice is None
    err = capsys.readouterr().err
    assert "ignoring configured voice 'Matilda'" in err
    assert "'polly'" in err


def test_config_voice_kept_for_same_provider(el_cfg, capsys):
    args = _args(provider="elevenlabs", voice="Matilda")
    _apply_voice_provider_scope(args, el_cfg, ["hello"])
    assert args.voice == "Matilda"
    assert capsys.readouterr().err == ""


def test_explicit_voice_flag_respected(el_cfg):
    args = _args(provider="polly", voice="Matilda")
    _apply_voice_provider_scope(args, el_cfg, ["-v", "Matilda", "hello"])
    assert args.voice == "Matilda"

    args = _args(provider="polly", voice="Matilda")
    _apply_voice_provider_scope(args, el_cfg, ["--voice=Matilda", "hello"])
    assert args.voice == "Matilda"


def test_env_voice_respected(el_cfg, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GENSAY_VOICE", "Matilda")
    args = _args(provider="polly", voice="Matilda")
    _apply_voice_provider_scope(args, el_cfg, ["hello"])
    assert args.voice == "Matilda"


def test_voice_without_config_provider_is_unscoped(capsys):
    cfg = UserConfig(provider=None, voice="Matilda")
    args = _args(provider="polly", voice="Matilda")
    _apply_voice_provider_scope(args, cfg, ["hello"])
    assert args.voice == "Matilda"
    assert capsys.readouterr().err == ""


def test_voice_flag_explicit():
    assert _voice_flag_explicit(["-v", "Alex"])
    assert _voice_flag_explicit(["--voice", "Alex"])
    assert _voice_flag_explicit(["--voice=Alex"])
    assert _voice_flag_explicit(["-vAlex"])
    assert not _voice_flag_explicit(["--via-daemon"])
    assert not _voice_flag_explicit(["-V", "hello", "say"])
    assert not _voice_flag_explicit(["hello"])
    assert not _voice_flag_explicit(["-r", "170"])
