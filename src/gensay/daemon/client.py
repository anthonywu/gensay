"""Client for talking to a running gensay daemon."""

from __future__ import annotations

import contextlib
import socket
import time
from pathlib import Path
from typing import Any

from .paths import DaemonPaths, default_paths
from .protocol import (
    DaemonRequest,
    DaemonResponse,
    ProtocolError,
    ResultBody,
    read_frame,
    write_frame,
)


class DaemonClientError(RuntimeError):
    """Base client error."""


class DaemonNotRunning(DaemonClientError):
    """No daemon reachable at the configured socket."""


class DaemonRPCError(DaemonClientError):
    """Daemon returned ok=false."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class DaemonClient:
    """Thin AF_UNIX client."""

    def __init__(self, paths: DaemonPaths | None = None, connect_timeout_s: float = 2.0):
        self.paths = paths or default_paths()
        self.connect_timeout_s = connect_timeout_s

    def is_running(self) -> bool:
        try:
            self.ping()
            return True
        except DaemonNotRunning:
            return False

    def ping(self) -> ResultBody:
        return self.request(DaemonRequest(cmd="ping")).result or ResultBody()

    def status(self) -> ResultBody:
        return self.request(DaemonRequest(cmd="status")).result or ResultBody()

    def speak(
        self,
        text: str,
        *,
        voice: str | None = None,
        rate: int | None = None,
        no_cache: bool = False,
        timeout_s: float | None = None,
        provider: str | None = None,
    ) -> ResultBody:
        resp = self.request(
            DaemonRequest(
                cmd="speak",
                text=text,
                voice=voice,
                rate=rate,
                no_cache=no_cache,
                timeout_s=timeout_s,
                provider=provider,
            ),
            timeout_s=timeout_s or 600.0,
        )
        return resp.result or ResultBody()

    def save(
        self,
        text: str,
        output: str | Path,
        *,
        voice: str | None = None,
        rate: int | None = None,
        format: str | None = None,
        no_cache: bool = False,
        timeout_s: float | None = None,
        provider: str | None = None,
    ) -> ResultBody:
        resp = self.request(
            DaemonRequest(
                cmd="save",
                text=text,
                voice=voice,
                rate=rate,
                output=str(output),
                format=format,
                no_cache=no_cache,
                timeout_s=timeout_s,
                provider=provider,
            ),
            timeout_s=timeout_s or 600.0,
        )
        return resp.result or ResultBody()

    def list_voices(self) -> list[dict[str, Any]]:
        result = self.request(DaemonRequest(cmd="list_voices")).result or ResultBody()
        return result.voices or []

    def shutdown(self) -> None:
        try:
            self.request(DaemonRequest(cmd="shutdown"), timeout_s=5.0)
        except (DaemonNotRunning, ProtocolError, OSError):
            # Daemon may close before reply; treat as success if socket gone
            if self.paths.socket.exists():
                raise

    def request(self, req: DaemonRequest, timeout_s: float | None = None) -> DaemonResponse:
        sock = self._connect()
        try:
            if timeout_s is not None:
                sock.settimeout(timeout_s)
            write_frame(sock, req.to_dict())
            data = read_frame(sock)
            resp = DaemonResponse.from_dict(data)
            if not resp.ok:
                err = resp.error
                raise DaemonRPCError(
                    err.code if err else "error",
                    err.message if err else "unknown error",
                )
            return resp
        finally:
            with contextlib.suppress(OSError):
                sock.close()

    def wait_until_ready(
        self,
        timeout_s: float = 60.0,
        *,
        require_model: bool = False,
        poll_s: float = 0.1,
    ) -> ResultBody:
        """Poll until daemon accepts connections (and optionally model is loaded)."""
        deadline = time.monotonic() + timeout_s
        last_err: Exception | None = None
        while time.monotonic() < deadline:
            try:
                st = self.status()
                if require_model and not st.model_loaded:
                    time.sleep(poll_s)
                    continue
                return st
            except (DaemonNotRunning, DaemonClientError, OSError, ProtocolError) as e:
                last_err = e
                time.sleep(poll_s)
        raise DaemonNotRunning(
            f"daemon not ready within {timeout_s}s"
            + (f" (last error: {last_err})" if last_err else "")
        )

    def _connect(self) -> socket.socket:
        path = self.paths.socket
        if not path.exists():
            raise DaemonNotRunning(f"no socket at {path}")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.connect_timeout_s)
        try:
            sock.connect(str(path))
        except OSError as e:
            sock.close()
            raise DaemonNotRunning(f"cannot connect to {path}: {e}") from e
        return sock
