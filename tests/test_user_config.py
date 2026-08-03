"""Tests for per-user XDG/platformdirs config defaults."""

from __future__ import annotations

from pathlib import Path

import pytest

from gensay.main import create_parser, get_default_provider
from gensay.user_config import (
    apply_env_overrides,
    load_user_config,
    resolve_user_config,
    write_example_config,
)


def test_load_missing_returns_empty(tmp_path: Path):
    cfg = load_user_config(tmp_path / "missing.toml")
    assert cfg.loaded is False
    assert cfg.provider is None
    assert cfg.main_cli_defaults() == {}


def test_load_toml_defaults(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
provider = "mock"
voice = "mock-voice-1"
rate = 200
auto_daemon = true
via_daemon = false
chunk_size = 250

[daemon]
provider = "mock"
idle_unload_s = 30
""",
        encoding="utf-8",
    )
    cfg = load_user_config(path)
    assert cfg.loaded is True
    assert cfg.provider == "mock"
    assert cfg.voice == "mock-voice-1"
    assert cfg.rate == 200
    assert cfg.auto_daemon is True
    assert cfg.chunk_size == 250
    assert cfg.daemon.provider == "mock"
    assert cfg.daemon.idle_unload_s == 30.0


def test_env_overrides_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "config.toml"
    path.write_text('provider = "mock"\nauto_daemon = false\n', encoding="utf-8")
    monkeypatch.setenv("GENSAY_PROVIDER", "macos")
    monkeypatch.setenv("GENSAY_AUTO_DAEMON", "1")
    cfg = apply_env_overrides(load_user_config(path))
    assert cfg.provider == "macos"
    assert cfg.auto_daemon is True


def test_parser_uses_user_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "config.toml"
    path.write_text(
        """
provider = "mock"
voice = "mock-voice-2"
rate = 180
auto_daemon = true
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GENSAY_CONFIG", str(path))
    # Clear provider env so file wins
    monkeypatch.delenv("GENSAY_PROVIDER", raising=False)
    monkeypatch.delenv("GENSAY_AUTO_DAEMON", raising=False)

    cfg = resolve_user_config()
    parser = create_parser(cfg)
    args = parser.parse_args(["hello"])
    assert args.provider == "mock"
    assert args.voice == "mock-voice-2"
    assert args.rate == 180
    assert args.auto_daemon is True
    assert args.message == ["hello"]


def test_cli_flag_overrides_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "config.toml"
    path.write_text('provider = "mock"\nauto_daemon = true\n', encoding="utf-8")
    monkeypatch.setenv("GENSAY_CONFIG", str(path))
    monkeypatch.delenv("GENSAY_PROVIDER", raising=False)

    cfg = resolve_user_config()
    parser = create_parser(cfg)
    args = parser.parse_args(["--provider", "macos", "--no-auto-daemon", "hi"])
    assert args.provider == "macos"
    assert args.auto_daemon is False


def test_get_default_provider_from_config():
    assert get_default_provider("mock") == "mock"
    assert get_default_provider("not-a-provider") in ("macos", "chatterbox")


def test_write_example_config(tmp_path: Path):
    path = tmp_path / "gensay" / "config.toml"
    written = write_example_config(path)
    assert written == path
    assert path.is_file()
    assert "provider" in path.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_example_config(path)
    write_example_config(path, force=True)


def test_config_cli_path_and_show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "config.toml"
    path.write_text('provider = "mock"\n', encoding="utf-8")
    monkeypatch.setenv("GENSAY_CONFIG", str(path))
    monkeypatch.delenv("GENSAY_PROVIDER", raising=False)

    from gensay.main import config_main

    config_main(["path"])
    config_main(["show"])
    config_main(["show", "--json"])


def test_config_set_get_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "config.toml"
    monkeypatch.setenv("GENSAY_CONFIG", str(path))

    from gensay.user_config import (
        get_config_value,
        load_user_config,
        set_config_value,
        unset_config_value,
    )

    set_config_value("provider", "mock")
    set_config_value("auto_daemon", "true")
    set_config_value("rate", "175")
    set_config_value("daemon.provider", "mock")
    set_config_value("daemon.idle_unload_s", "45")

    assert get_config_value("provider") == "mock"
    assert get_config_value("auto_daemon") is True
    assert get_config_value("rate") == 175
    assert get_config_value("daemon.provider") == "mock"
    assert get_config_value("daemon.idle_unload_s") == 45.0

    cfg = load_user_config()
    assert cfg.provider == "mock"
    assert cfg.auto_daemon is True
    assert cfg.daemon.idle_unload_s == 45.0

    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert 'provider = "mock"' in text
    assert "auto_daemon = true" in text
    assert "[daemon]" in text

    assert unset_config_value("rate") is True
    assert get_config_value("rate") is None
    assert unset_config_value("rate") is False


def test_config_set_invalid_key_and_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from gensay.user_config import ConfigKeyError, ConfigValueError, set_config_value

    monkeypatch.setenv("GENSAY_CONFIG", str(tmp_path / "c.toml"))
    with pytest.raises(ConfigKeyError):
        set_config_value("not_a_key", "x")
    with pytest.raises(ConfigValueError):
        set_config_value("auto_daemon", "maybe")
    with pytest.raises(ConfigValueError):
        set_config_value("rate", "fast")


def test_config_cli_get_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    path = tmp_path / "config.toml"
    monkeypatch.setenv("GENSAY_CONFIG", str(path))

    from gensay.main import config_main

    config_main(["set", "provider", "mock"])
    config_main(["set", "auto_daemon", "true"])
    config_main(["get", "provider"])
    out = capsys.readouterr().out
    assert "mock" in out

    config_main(["get", "auto_daemon"])
    assert "true" in capsys.readouterr().out

    config_main(["keys"])
    keys_out = capsys.readouterr().out
    assert "provider" in keys_out
    assert "daemon.provider" in keys_out

    config_main(["unset", "provider"])
    capsys.readouterr()  # discard unset chatter
    with pytest.raises(SystemExit) as ei:
        config_main(["get", "provider"])
    assert ei.value.code == 1
    capsys.readouterr()

    config_main(["get", "provider", "--default", ""])
    assert capsys.readouterr().out.strip() == ""
