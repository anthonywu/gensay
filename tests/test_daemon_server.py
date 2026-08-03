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
