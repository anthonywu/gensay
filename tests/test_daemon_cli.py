"""In-process tests for `gensay daemon ...` CLI flows (daemon_main).

Lifecycle/server are monkeypatched — these tests cover argument parsing,
subcommand dispatch, and output formatting, not actual process management.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from gensay.main import daemon_main


@pytest.fixture
def isolated_runtime(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Keep daemon paths + user config out of the real user environment."""
    monkeypatch.setenv("GENSAY_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("GENSAY_SOCKET", str(tmp_path / "run" / "s.sock"))
    monkeypatch.setenv("GENSAY_CONFIG", str(tmp_path / "missing-config.toml"))
    # Guard against GENSAY_DAEMON_* env leaking into parser defaults
    for var in (
        "GENSAY_DAEMON_PROVIDER",
        "GENSAY_DAEMON_IDLE_UNLOAD_S",
        "GENSAY_DAEMON_IDLE_EXIT_S",
        "GENSAY_DAEMON_START_TIMEOUT_S",
    ):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


@pytest.fixture
def fake_lifecycle(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from gensay.daemon import lifecycle

    calls: dict[str, list] = {"start": [], "stop": [], "status": []}
    st = SimpleNamespace(pid=4242, provider="mock", model_loaded=True)

    monkeypatch.setattr(
        lifecycle,
        "start_detached",
        lambda provider, **kw: calls["start"].append((provider, kw)) or st,
    )
    monkeypatch.setattr(lifecycle, "stop", lambda paths: calls["stop"].append(paths))
    monkeypatch.setattr(
        lifecycle,
        "status",
        lambda paths: (
            (calls["status"].append(paths))
            or {
                "running": False,
                "socket": str(tmp_path / "run" / "s.sock"),
                "pidfile": str(tmp_path / "run" / "s.pid"),
                "pid": None,
            }
        ),
    )
    return SimpleNamespace(calls=calls, started=st)


def test_daemon_status_not_running(isolated_runtime, fake_lifecycle, capsys):
    daemon_main(["status"])
    out = capsys.readouterr().out
    assert "running: no" in out
    assert "socket:" in out
    assert len(fake_lifecycle.calls["status"]) == 1


def test_daemon_status_json(isolated_runtime, fake_lifecycle, capsys):
    daemon_main(["status", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["running"] is False
    assert "socket" in data


def test_daemon_status_running(isolated_runtime, fake_lifecycle, monkeypatch, capsys):
    from gensay.daemon import lifecycle

    monkeypatch.setattr(
        lifecycle,
        "status",
        lambda paths: {
            "running": True,
            "socket": "/tmp/s.sock",
            "pid": 4242,
            "provider": "mock",
            "model_loaded": True,
            "device": "cpu",
            "uptime_s": 61,
            "queue_depth": 0,
            "idle_s": 3,
            "version": "0.4.2",
        },
    )
    daemon_main(["status"])
    out = capsys.readouterr().out
    assert "running: yes" in out
    assert "provider: mock" in out
    assert "model_loaded: True" in out
    assert "version: 0.4.2" in out


def test_daemon_stop(isolated_runtime, fake_lifecycle, capsys):
    daemon_main(["stop"])
    assert len(fake_lifecycle.calls["stop"]) == 1
    assert "daemon stopped" in capsys.readouterr().out


def test_daemon_start_passes_flags(isolated_runtime, fake_lifecycle, capsys):
    daemon_main(
        [
            "start",
            "-p",
            "mock",
            "--no-preload",
            "--no-cache",
            "--idle-unload-s",
            "30",
            "--idle-exit-s",
            "0",
            "--ready-timeout",
            "5",
        ]
    )
    out = capsys.readouterr().out
    ((provider, kw),) = fake_lifecycle.calls["start"]
    assert provider == "mock"
    assert kw["preload"] is False
    assert kw["no_cache"] is True
    assert kw["idle_unload_s"] == 30.0
    assert kw["idle_exit_s"] == 0.0
    assert kw["ready_timeout_s"] == 5.0
    assert "started gensay daemon pid=4242 provider=mock model_loaded=True" in out
    assert "socket=" in out


def test_daemon_start_error_exits_1(isolated_runtime, fake_lifecycle, monkeypatch, capsys):
    from gensay.daemon import lifecycle

    def boom(provider, **kw):
        raise lifecycle.LifecycleError("startup timed out")

    monkeypatch.setattr(lifecycle, "start_detached", boom)
    with pytest.raises(SystemExit) as ei:
        daemon_main(["start", "-p", "mock"])
    assert ei.value.code == 1
    assert "startup timed out" in capsys.readouterr().err


def test_daemon_restart_stops_then_starts(isolated_runtime, fake_lifecycle, capsys):
    daemon_main(["restart", "-p", "mock"])
    assert len(fake_lifecycle.calls["stop"]) == 1
    assert len(fake_lifecycle.calls["start"]) == 1
    assert "started gensay daemon" in capsys.readouterr().out


def test_daemon_restart_tolerates_stop_failure(
    isolated_runtime, fake_lifecycle, monkeypatch, capsys
):
    from gensay.daemon import lifecycle

    monkeypatch.setattr(
        lifecycle, "stop", lambda paths: (_ for _ in ()).throw(RuntimeError("not running"))
    )
    daemon_main(["restart", "-p", "mock"])
    assert len(fake_lifecycle.calls["start"]) == 1


def test_daemon_run_foreground(isolated_runtime, monkeypatch):
    seen = {}

    def fake_run_server(provider, *, config, paths, preload, idle_unload_s, idle_exit_s):
        seen.update(
            provider=provider,
            config=config,
            preload=preload,
            idle_unload_s=idle_unload_s,
            idle_exit_s=idle_exit_s,
        )

    monkeypatch.setattr("gensay.daemon.server.run_server", fake_run_server)
    daemon_main(["run", "-p", "mock", "--no-preload", "--idle-exit-s", "900"])

    assert seen["provider"] == "mock"
    assert seen["preload"] is False
    assert seen["idle_exit_s"] == 900.0
    # daemon config: no progress UI, small chunks
    assert seen["config"].extra == {"show_progress": False, "chunk_size": 500}
