"""Daemon process lifecycle: start detached, stop, status, pidfile."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time

from .client import DaemonClient, DaemonNotRunning
from .paths import DaemonPaths, default_paths
from .protocol import ResultBody


class LifecycleError(RuntimeError):
    pass


def read_pid(paths: DaemonPaths) -> int | None:
    if not paths.pidfile.exists():
        return None
    try:
        return int(paths.pidfile.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def status(paths: DaemonPaths | None = None) -> dict:
    """Return a status dict for CLI printing."""
    paths = paths or default_paths()
    client = DaemonClient(paths)
    base = {
        "running": False,
        "socket": str(paths.socket),
        "pidfile": str(paths.pidfile),
        "pid": read_pid(paths),
    }
    try:
        st = client.status()
        base.update(
            {
                "running": True,
                "pid": st.pid or base["pid"],
                "provider": st.provider,
                "model_loaded": st.model_loaded,
                "device": st.device,
                "uptime_s": st.uptime_s,
                "queue_depth": st.queue_depth,
                "idle_s": st.idle_s,
                "version": st.version,
            }
        )
        return base
    except DaemonNotRunning:
        pid = base["pid"]
        if pid and pid_is_alive(pid):
            base["note"] = "pidfile present but socket not responding"
        return base


def stop(paths: DaemonPaths | None = None, timeout_s: float = 10.0) -> None:
    paths = paths or default_paths()
    client = DaemonClient(paths)
    pid = read_pid(paths)

    if client.is_running():
        with contextlib.suppress(Exception):
            client.shutdown()
        # Wait for socket to disappear
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if not paths.socket.exists() and not client.is_running():
                _cleanup_files(paths)
                return
            time.sleep(0.1)

    # Fallback: SIGTERM via pidfile
    if pid and pid_is_alive(pid):
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if not pid_is_alive(pid):
                _cleanup_files(paths)
                return
            time.sleep(0.1)
        os.kill(pid, signal.SIGKILL)

    _cleanup_files(paths)


def start_detached(
    provider: str,
    *,
    paths: DaemonPaths | None = None,
    voice: str | None = None,
    rate: int | None = None,
    preload: bool = True,
    idle_unload_s: float = 0.0,
    idle_exit_s: float = 0.0,
    no_cache: bool = False,
    ready_timeout_s: float = 120.0,
    extra_env: dict[str, str] | None = None,
) -> ResultBody:
    """Spawn `gensay daemon run` in the background and wait until ready."""
    paths = paths or default_paths()
    paths.ensure_runtime_dir()

    client = DaemonClient(paths)
    if client.is_running():
        st = client.status()
        if st.provider and st.provider != provider:
            raise LifecycleError(
                f"daemon already running with provider={st.provider!r}; "
                f"stop it before starting provider={provider!r}"
            )
        return st

    cmd = [
        sys.executable,
        "-m",
        "gensay",
        "daemon",
        "run",
        "--provider",
        provider,
        "--socket",
        str(paths.socket),
        "--runtime-dir",
        str(paths.runtime_dir),
    ]
    if voice:
        cmd.extend(["--voice", voice])
    if rate is not None:
        cmd.extend(["--rate", str(rate)])
    if not preload:
        cmd.append("--no-preload")
    if idle_unload_s > 0:
        cmd.extend(["--idle-unload-s", str(idle_unload_s)])
    if idle_exit_s > 0:
        cmd.extend(["--idle-exit-s", str(idle_exit_s)])
    if no_cache:
        cmd.append("--no-cache")

    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    env["GENSAY_RUNTIME_DIR"] = str(paths.runtime_dir)
    env["GENSAY_SOCKET"] = str(paths.socket)

    log_path = paths.runtime_dir / "daemon.log"
    log_f = open(log_path, "a", encoding="utf-8")  # noqa: SIM115 — kept open for child lifetime
    try:
        subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
            close_fds=True,
        )
    finally:
        log_f.close()

    return client.wait_until_ready(
        timeout_s=ready_timeout_s,
        require_model=preload,
    )


def _cleanup_files(paths: DaemonPaths) -> None:
    for p in (paths.socket, paths.pidfile):
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass
