"""Integration tests: in-process daemon server + client over AF_UNIX."""

from __future__ import annotations

import shutil
import threading
import time
import uuid
from pathlib import Path

import pytest

from gensay.daemon.client import DaemonClient, DaemonNotRunning, DaemonRPCError
from gensay.daemon.paths import DaemonPaths
from gensay.daemon.server import DaemonServer
from gensay.providers.base import TTSConfig
from gensay.providers.mock import MockProvider


@pytest.fixture
def daemon_paths() -> DaemonPaths:
    # macOS AF_UNIX sun_path is ~104 bytes; pytest tmp_path is often too long.
    runtime = Path("/tmp") / f"gsd-{uuid.uuid4().hex[:10]}"
    runtime.mkdir(mode=0o700)
    paths = DaemonPaths(
        runtime_dir=runtime,
        socket=runtime / "s.sock",
        pidfile=runtime / "s.pid",
        lockfile=runtime / "s.lock",
    )
    yield paths
    shutil.rmtree(runtime, ignore_errors=True)


@pytest.fixture
def running_daemon(daemon_paths: DaemonPaths):
    config = TTSConfig(extra={"simulate_delay": False, "show_progress": False})
    provider = MockProvider(config)
    server = DaemonServer(
        provider,
        provider_name="mock",
        paths=daemon_paths,
        preload=True,
    )
    thread = threading.Thread(target=server.start, name="test-daemon", daemon=True)
    thread.start()

    client = DaemonClient(daemon_paths, connect_timeout_s=1.0)
    client.wait_until_ready(timeout_s=5.0, require_model=True)

    yield server, client, provider

    server.stop()
    thread.join(timeout=3.0)


def test_ping_and_status(running_daemon):
    server, client, provider = running_daemon
    ping = client.ping()
    assert ping.provider == "mock"
    assert ping.pid is not None

    st = client.status()
    assert st.provider == "mock"
    assert st.model_loaded is True
    assert st.pid == ping.pid
    assert provider.warmup_calls >= 1


def test_speak_records_text(running_daemon):
    _server, client, provider = running_daemon
    result = client.speak("hello daemon")
    assert result.elapsed_ms is not None
    assert provider.last_spoken_text == "hello daemon"


def test_save_writes_file(running_daemon, tmp_path: Path):
    _server, client, provider = running_daemon
    out = tmp_path / "out.wav"
    result = client.save("save me", out, format="wav")
    assert result.path == str(out)
    assert out.exists()
    assert provider.last_saved_file == out


def test_list_voices(running_daemon):
    _server, client, _provider = running_daemon
    voices = client.list_voices()
    assert len(voices) >= 1
    assert "id" in voices[0]


def test_provider_mismatch(running_daemon):
    _server, client, _provider = running_daemon
    with pytest.raises(DaemonRPCError) as ei:
        client.speak("x", provider="chatterbox")
    assert ei.value.code == "provider_mismatch"
    assert "active gensay daemon hosting 'mock'" in ei.value.message
    assert "drop -p/--provider" in ei.value.message
    assert "gensay daemon restart -p chatterbox" in ei.value.message


def test_bad_request_missing_text(running_daemon):
    _server, client, _provider = running_daemon
    from gensay.daemon.protocol import DaemonRequest

    with pytest.raises(DaemonRPCError) as ei:
        client.request(DaemonRequest(cmd="speak", text=None))
    assert ei.value.code == "bad_request"


def test_not_running(daemon_paths: DaemonPaths):
    client = DaemonClient(daemon_paths)
    with pytest.raises(DaemonNotRunning):
        client.ping()


def test_shutdown(daemon_paths: DaemonPaths):
    config = TTSConfig(extra={"simulate_delay": False, "show_progress": False})
    provider = MockProvider(config)
    server = DaemonServer(provider, provider_name="mock", paths=daemon_paths, preload=True)
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    client = DaemonClient(daemon_paths)
    client.wait_until_ready(timeout_s=5.0)

    client.shutdown()
    # give server time to exit
    deadline = time.time() + 3
    while time.time() < deadline and daemon_paths.socket.exists():
        time.sleep(0.05)
    thread.join(timeout=3.0)
    assert not client.is_running()


def _run_server(daemon_paths: DaemonPaths, provider: MockProvider, **server_kw):
    """Start a server inline (for tests needing custom idle/preload settings)."""
    server = DaemonServer(provider, provider_name="mock", paths=daemon_paths, **server_kw)
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    client = DaemonClient(daemon_paths)
    return server, thread, client


def _teardown(server, thread, client):
    server.stop()
    thread.join(timeout=3.0)
    assert not client.is_running()


def _wait_for(cond, timeout_s: float = 4.0, msg: str = "condition not met") -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if cond():
            return
        time.sleep(0.05)
    raise AssertionError(msg)


def test_idle_unload_releases_model_and_rewarms_on_demand(daemon_paths: DaemonPaths):
    config = TTSConfig(extra={"simulate_delay": False, "show_progress": False})
    provider = MockProvider(config)
    server, thread, client = _run_server(daemon_paths, provider, preload=True, idle_unload_s=0.5)
    client.wait_until_ready(timeout_s=5.0, require_model=True)
    assert provider.warmup_calls == 1

    _wait_for(lambda: provider.unload_calls == 1, msg="model should unload when idle")
    assert server.model_loaded is False

    client.speak("hello again")
    assert provider.warmup_calls == 2  # re-warmed on demand

    _teardown(server, thread, client)


def test_idle_exit_stops_server_process(daemon_paths: DaemonPaths):
    config = TTSConfig(extra={"simulate_delay": False, "show_progress": False})
    provider = MockProvider(config)
    server, thread, client = _run_server(daemon_paths, provider, preload=False, idle_exit_s=0.5)
    client.wait_until_ready(timeout_s=5.0)

    def gone():
        return not client.is_running()

    _wait_for(gone, msg="server should exit itself when idle")
    thread.join(timeout=3.0)


def test_malformed_frame_gets_bad_request(daemon_paths: DaemonPaths):
    import socket as pysock

    from gensay.daemon.protocol import read_frame, write_frame

    config = TTSConfig(extra={"simulate_delay": False, "show_progress": False})
    provider = MockProvider(config)
    server, thread, client = _run_server(daemon_paths, provider, preload=True)
    client.wait_until_ready(timeout_s=5.0)
    try:
        # valid framing, unknown command
        raw = pysock.socket(pysock.AF_UNIX, pysock.SOCK_STREAM)
        raw.settimeout(2.0)
        raw.connect(str(daemon_paths.socket))
        write_frame(raw, {"v": 1, "id": "t1", "cmd": "explode"})
        resp = read_frame(raw)
        raw.close()
        assert resp["ok"] is False
        assert resp["error"]["code"] == "bad_request"

        # invalid JSON payload
        raw = pysock.socket(pysock.AF_UNIX, pysock.SOCK_STREAM)
        raw.settimeout(2.0)
        raw.connect(str(daemon_paths.socket))
        raw.sendall(b"\x00\x00\x00\x04garb")
        resp = read_frame(raw)
        raw.close()
        assert resp["ok"] is False
        assert resp["error"]["code"] == "bad_request"
    finally:
        _teardown(server, thread, client)


def test_speak_inference_error_surfaces_as_rpc_error(running_daemon):
    _server, client, provider = running_daemon

    def boom(text, voice=None, rate=None):
        raise RuntimeError("synthesis exploded")

    provider.speak = boom
    with pytest.raises(DaemonRPCError, match="inference_error"):
        client.speak("boom")


def test_speak_not_loaded_when_warmup_fails(daemon_paths: DaemonPaths):
    config = TTSConfig(extra={"simulate_delay": False, "show_progress": False})
    provider = MockProvider(config)
    provider.warmup = lambda: (_ for _ in ()).throw(RuntimeError("cannot load model"))
    server, thread, client = _run_server(daemon_paths, provider, preload=False)
    client.wait_until_ready(timeout_s=5.0, require_model=False)
    try:
        with pytest.raises(DaemonRPCError, match="not_loaded"):
            client.speak("hello")
    finally:
        _teardown(server, thread, client)


def test_start_raises_when_socket_already_listening(daemon_paths: DaemonPaths):
    import socket as pysock

    blocker = pysock.socket(pysock.AF_UNIX, pysock.SOCK_STREAM)
    blocker.bind(str(daemon_paths.socket))
    blocker.listen(1)
    try:
        config = TTSConfig(extra={"simulate_delay": False, "show_progress": False})
        server = DaemonServer(
            MockProvider(config), provider_name="mock", paths=daemon_paths, preload=False
        )
        with pytest.raises(RuntimeError, match="already listening"):
            server.start()
    finally:
        blocker.close()
