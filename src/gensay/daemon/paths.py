"""Runtime paths for the gensay daemon (socket, pidfile, lock)."""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from pathlib import Path

import platformdirs

SOCKET_NAME = "gensay.sock"
PID_NAME = "gensay.pid"
LOCK_NAME = "gensay.daemon.lock"


@dataclass(frozen=True)
class DaemonPaths:
    """Filesystem locations for a single user-local daemon instance."""

    runtime_dir: Path
    socket: Path
    pidfile: Path
    lockfile: Path

    def ensure_runtime_dir(self) -> None:
        self.runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            self.runtime_dir.chmod(0o700)


def default_paths(
    runtime_dir: Path | str | None = None,
    socket: Path | str | None = None,
) -> DaemonPaths:
    """Resolve daemon paths from args/env/platformdirs."""
    if runtime_dir is not None:
        rdir = Path(runtime_dir)
    elif env := os.environ.get("GENSAY_RUNTIME_DIR"):
        rdir = Path(env)
    else:
        rdir = Path(platformdirs.user_runtime_dir("gensay", "gensay"))

    if socket is not None:
        sock = Path(socket)
    elif env_sock := os.environ.get("GENSAY_SOCKET"):
        sock = Path(env_sock)
    else:
        sock = rdir / SOCKET_NAME

    return DaemonPaths(
        runtime_dir=rdir,
        socket=sock,
        pidfile=rdir / PID_NAME,
        lockfile=rdir / LOCK_NAME,
    )
