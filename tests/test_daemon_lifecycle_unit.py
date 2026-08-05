"""In-process unit tests for daemon lifecycle error paths.

Complements test_daemon_lifecycle.py (subprocess integration): here we stub
DaemonClient / Popen / os.kill directly to cover cheap failure semantics.
"""

from __future__ import annotations

import signal
from types import SimpleNamespace

import pytest

from gensay.daemon import lifecycle
from gensay.daemon.lifecycle import LifecycleError, read_pid
from gensay.daemon.paths import DaemonPaths


@pytest.fixture
def paths(tmp_path) -> DaemonPaths:
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    p = DaemonPaths(
        runtime_dir=runtime,
        socket=runtime / "s.sock",
        pidfile=runtime / "s.pid",
        lockfile=runtime / "s.lock",
    )
    p.ensure_runtime_dir()
    return p


class FakeClient:
    """Stand-in for DaemonClient, configured per test."""

    def __init__(self, paths):
        self.is_running_calls = 0

    # per-class attributes overridable by tests
    running = False
    status_body = None
    raise_not_running = False

    def is_running(self) -> bool:
        self.is_running_calls += 1
        return self.running

    def status(self):
        if self.raise_not_running:
            raise lifecycle.DaemonNotRunning("no socket")
        return self.status_body

    def shutdown(self):
        pass

    def wait_until_ready(self, timeout_s, require_model):
        return SimpleNamespace(pid=9999, provider="mock", model_loaded=True)


@pytest.fixture
def fake_client_cls(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(lifecycle, "DaemonClient", FakeClient)
    # reset class-level config between tests
    FakeClient.running = False
    FakeClient.status_body = None
    FakeClient.raise_not_running = False
    return FakeClient


def test_read_pid_missing_and_garbage(paths):
    assert read_pid(paths) is None
    paths.pidfile.write_text("not-a-pid", encoding="utf-8")
    assert read_pid(paths) is None
    paths.pidfile.write_text("4242\n", encoding="utf-8")
    assert read_pid(paths) == 4242


def test_status_not_running_with_stale_pidfile_note(paths, fake_client_cls, monkeypatch):
    FakeClient.raise_not_running = True
    paths.pidfile.write_text("12345", encoding="utf-8")
    monkeypatch.setattr(lifecycle, "pid_is_alive", lambda pid: True)

    st = lifecycle.status(paths)
    assert st["running"] is False
    assert st["pid"] == 12345
    assert st["note"] == "pidfile present but socket not responding"


def test_status_running_merges_fields(paths, fake_client_cls):
    FakeClient.raise_not_running = False
    FakeClient.status_body = SimpleNamespace(
        pid=777,
        provider="chatterbox",
        model_loaded=True,
        device="mps",
        uptime_s=42,
        queue_depth=1,
        idle_s=9,
        version="0.4.2",
    )
    st = lifecycle.status(paths)
    assert st["running"] is True
    assert st["provider"] == "chatterbox"
    assert st["model_loaded"] is True
    assert st["device"] == "mps"


def test_stop_not_running_cleans_up_files(paths, fake_client_cls):
    paths.socket.touch()
    paths.pidfile.write_text("12345", encoding="utf-8")

    lifecycle.stop(paths)

    assert not paths.socket.exists()
    assert not paths.pidfile.exists()


def test_stop_escalates_to_sigkill(paths, fake_client_cls, monkeypatch):
    kills: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "gensay.daemon.lifecycle.os.kill", lambda pid, sig: kills.append((pid, sig))
    )
    monkeypatch.setattr(lifecycle, "pid_is_alive", lambda pid: True)
    paths.pidfile.write_text("4242", encoding="utf-8")

    lifecycle.stop(paths, timeout_s=0)

    assert kills == [(4242, signal.SIGTERM), (4242, signal.SIGKILL)]
    assert not paths.pidfile.exists()


def test_stop_running_daemon_shutdowns_then_removes_socket(paths, fake_client_cls, monkeypatch):
    paths.socket.touch()

    fake_client_cls.running = True

    shutdowns: list[bool] = []

    def shutdown(self):
        shutdowns.append(True)
        paths.socket.unlink()  # simulate server unlinking its socket on exit
        type(self).running = False

    monkeypatch.setattr(FakeClient, "shutdown", shutdown)

    lifecycle.stop(paths, timeout_s=2)

    assert shutdowns == [True]
    assert not paths.socket.exists()


def test_start_detached_already_running_same_provider_skips_spawn(
    paths, fake_client_cls, monkeypatch
):
    FakeClient.running = True
    FakeClient.status_body = SimpleNamespace(provider="mock", pid=1, model_loaded=True)
    popen_calls: list = []
    monkeypatch.setattr(
        "gensay.daemon.lifecycle.subprocess.Popen",
        lambda *a, **kw: popen_calls.append((a, kw)),
    )

    st = lifecycle.start_detached("mock", paths=paths)

    assert st.provider == "mock"
    assert popen_calls == []


def test_start_detached_provider_mismatch_raises(paths, fake_client_cls, monkeypatch):
    FakeClient.running = True
    FakeClient.status_body = SimpleNamespace(provider="chatterbox", pid=1, model_loaded=False)

    with pytest.raises(LifecycleError, match="already running with provider='chatterbox'"):
        lifecycle.start_detached("mock", paths=paths)


def test_start_detached_forwards_flags_and_env(paths, fake_client_cls, monkeypatch, tmp_path):
    FakeClient.running = False
    spawned: dict = {}

    class FakePopen:
        def __init__(self, cmd, **kw):
            spawned["cmd"] = cmd
            spawned["env"] = kw["env"]

    monkeypatch.setattr("gensay.daemon.lifecycle.subprocess.Popen", FakePopen)

    lifecycle.start_detached(
        "mock",
        paths=paths,
        voice="bob",
        rate=200,
        preload=False,
        idle_unload_s=30,
        idle_exit_s=60,
        no_cache=True,
        ready_timeout_s=5,
    )

    cmd = spawned["cmd"]
    joined = " ".join(str(c) for c in cmd)
    assert "daemon" in joined and "run" in joined
    idx = cmd.index("--provider")
    assert cmd[idx + 1] == "mock"
    for flag, val in (
        ("--voice", "bob"),
        ("--rate", "200"),
        ("--idle-unload-s", "30"),
        ("--idle-exit-s", "60"),
    ):
        fi = cmd.index(flag)
        assert cmd[fi + 1] == val
    assert "--no-preload" in cmd
    assert "--no-cache" in cmd
    assert spawned["env"]["GENSAY_SOCKET"] == str(paths.socket)
    assert spawned["env"]["GENSAY_RUNTIME_DIR"] == str(paths.runtime_dir)
