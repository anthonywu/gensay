"""Lifecycle tests: detached start/stop/status via CLI subprocess."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from gensay.daemon.client import DaemonClient
from gensay.daemon.paths import DaemonPaths


@pytest.fixture
def short_paths() -> DaemonPaths:
    runtime = Path("/tmp") / f"gsl-{uuid.uuid4().hex[:10]}"
    runtime.mkdir(mode=0o700)
    paths = DaemonPaths(
        runtime_dir=runtime,
        socket=runtime / "s.sock",
        pidfile=runtime / "s.pid",
        lockfile=runtime / "s.lock",
    )
    yield paths
    # best-effort stop
    env = os.environ.copy()
    env["GENSAY_RUNTIME_DIR"] = str(paths.runtime_dir)
    env["GENSAY_SOCKET"] = str(paths.socket)
    subprocess.run(
        [sys.executable, "-m", "gensay", "daemon", "stop"],
        env=env,
        capture_output=True,
        timeout=10,
    )
    shutil.rmtree(runtime, ignore_errors=True)


def _env_for(paths: DaemonPaths) -> dict[str, str]:
    env = os.environ.copy()
    env["GENSAY_RUNTIME_DIR"] = str(paths.runtime_dir)
    env["GENSAY_SOCKET"] = str(paths.socket)
    # Ensure package is importable from same interpreter
    return env


def test_daemon_start_status_stop(short_paths: DaemonPaths):
    env = _env_for(short_paths)
    start = subprocess.run(
        [
            sys.executable,
            "-m",
            "gensay",
            "daemon",
            "start",
            "-p",
            "mock",
            "--ready-timeout",
            "15",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert start.returncode == 0, start.stdout + start.stderr
    assert "started gensay daemon" in start.stdout
    assert "provider=mock" in start.stdout

    status = subprocess.run(
        [sys.executable, "-m", "gensay", "daemon", "status", "--json"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert status.returncode == 0, status.stderr
    data = json.loads(status.stdout)
    assert data["running"] is True
    assert data["provider"] == "mock"
    assert data["model_loaded"] is True

    # RPC speak through client
    client = DaemonClient(short_paths)
    client.speak("lifecycle ok")

    stop = subprocess.run(
        [sys.executable, "-m", "gensay", "daemon", "stop"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert stop.returncode == 0, stop.stderr
    assert not client.is_running()


def test_via_daemon_cli(short_paths: DaemonPaths):
    env = _env_for(short_paths)
    start = subprocess.run(
        [sys.executable, "-m", "gensay", "daemon", "start", "-p", "mock", "--ready-timeout", "15"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert start.returncode == 0, start.stderr

    speak = subprocess.run(
        [
            sys.executable,
            "-m",
            "gensay",
            "--provider",
            "mock",
            "--via-daemon",
            "hello via daemon",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert speak.returncode == 0, speak.stdout + speak.stderr
    # mock prints to stdout from daemon process, not client — client just exits 0

    subprocess.run(
        [sys.executable, "-m", "gensay", "daemon", "stop"],
        env=env,
        capture_output=True,
        timeout=15,
    )


def test_listen_removed_error():
    result = subprocess.run(
        [sys.executable, "-m", "gensay", "--listen", "hi"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "daemon" in result.stderr.lower()
