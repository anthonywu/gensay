"""Unix-domain socket server that keeps a TTS provider warm."""

from __future__ import annotations

import contextlib
import logging
import os
import queue
import signal
import socket
import threading
import time
import traceback
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..providers.base import AudioFormat, TTSConfig, TTSProvider
from .paths import DaemonPaths, default_paths
from .protocol import (
    DaemonRequest,
    DaemonResponse,
    ProtocolError,
    ResultBody,
    read_frame,
    write_frame,
)

log = logging.getLogger("gensay.daemon")


@dataclass
class _Job:
    request: DaemonRequest
    future: Future


class DaemonServer:
    """Accept AF_UNIX clients; serialize inference on a single worker thread."""

    def __init__(
        self,
        provider: TTSProvider,
        *,
        provider_name: str,
        paths: DaemonPaths | None = None,
        preload: bool = True,
        idle_unload_s: float = 0.0,
        idle_exit_s: float = 0.0,
        job_timeout_s: float = 600.0,
    ):
        self.provider = provider
        self.provider_name = provider_name
        self.paths = paths or default_paths()
        self.preload = preload
        self.idle_unload_s = idle_unload_s
        self.idle_exit_s = idle_exit_s
        self.job_timeout_s = job_timeout_s

        self._sock: socket.socket | None = None
        self._job_queue: queue.Queue[_Job | None] = queue.Queue()
        self._stop = threading.Event()
        self._accept_thread: threading.Thread | None = None
        self._worker_thread: threading.Thread | None = None
        self._idle_thread: threading.Thread | None = None

        self._started_at = time.time()
        self._model_loaded = False
        self._last_request_at: float | None = None
        self._device: str | None = None
        self._lock = threading.Lock()

    @property
    def model_loaded(self) -> bool:
        return self._model_loaded

    def start(self) -> None:
        """Bind socket, optionally preload model, start threads. Blocks until stop."""
        self.paths.ensure_runtime_dir()
        self._cleanup_stale_socket()
        self._bind()
        self._write_pid()

        self._worker_thread = threading.Thread(
            target=self._worker_loop, name="gensay-worker", daemon=True
        )
        self._worker_thread.start()

        if self.preload:
            self._do_warmup()

        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="gensay-accept", daemon=True
        )
        self._accept_thread.start()

        if self.idle_unload_s > 0 or self.idle_exit_s > 0:
            self._idle_thread = threading.Thread(
                target=self._idle_loop, name="gensay-idle", daemon=True
            )
            self._idle_thread.start()

        log.info(
            "daemon ready provider=%s socket=%s model_loaded=%s pid=%s",
            self.provider_name,
            self.paths.socket,
            self._model_loaded,
            os.getpid(),
        )

        # Block main thread until stop
        try:
            while not self._stop.is_set():
                self._stop.wait(timeout=0.5)
        finally:
            self._shutdown_internal()

    def stop(self) -> None:
        self._stop.set()

    def status_result(self) -> ResultBody:
        now = time.time()
        idle_s = None
        if self._last_request_at is not None:
            idle_s = now - self._last_request_at
        elif self._started_at:
            idle_s = now - self._started_at
        device = self._device
        if device is None and hasattr(self.provider, "_device"):
            device = getattr(self.provider, "_device", None)
        return ResultBody(
            pid=os.getpid(),
            uptime_s=round(now - self._started_at, 3),
            provider=self.provider_name,
            model_loaded=self._model_loaded,
            device=device,
            queue_depth=self._job_queue.qsize(),
            last_request_at=self._last_request_at,
            idle_s=round(idle_s, 3) if idle_s is not None else None,
            version=_package_version(),
        )

    # --- internals ---------------------------------------------------------

    def _bind(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            if self.paths.socket.exists():
                self.paths.socket.unlink()
            sock.bind(str(self.paths.socket))
            with contextlib.suppress(OSError):
                self.paths.socket.chmod(0o600)
            sock.listen(16)
            sock.settimeout(0.5)
            self._sock = sock
        except Exception:
            sock.close()
            raise

    def _write_pid(self) -> None:
        self.paths.pidfile.write_text(str(os.getpid()), encoding="utf-8")
        with contextlib.suppress(OSError):
            self.paths.pidfile.chmod(0o600)

    def _cleanup_stale_socket(self) -> None:
        if not self.paths.socket.exists():
            return
        # If something is still listening, leave it (start path should have checked)
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(0.2)
        try:
            probe.connect(str(self.paths.socket))
            probe.close()
            raise RuntimeError(f"daemon already listening on {self.paths.socket}")
        except OSError:
            probe.close()
            with contextlib.suppress(OSError):
                self.paths.socket.unlink()

    def _do_warmup(self) -> None:
        try:
            if hasattr(self.provider, "warmup"):
                self.provider.warmup()
            self._model_loaded = True
            if hasattr(self.provider, "_device"):
                self._device = getattr(self.provider, "_device", None)
            log.info("warmup complete provider=%s", self.provider_name)
        except Exception:
            log.exception("warmup failed")
            # Stay up; speak will retry / error

    def _accept_loop(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                if self._stop.is_set():
                    break
                continue
            t = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
            t.start()

    def _handle_client(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(self.job_timeout_s + 5.0)
            raw = read_frame(conn)
            req = DaemonRequest.from_dict(raw)
            resp = self._dispatch(req)
            write_frame(conn, resp.to_dict())
        except ProtocolError as e:
            with contextlib.suppress(OSError):
                write_frame(
                    conn,
                    {
                        "v": 1,
                        "id": "",
                        "ok": False,
                        "cmd": "",
                        "error": {"code": "bad_request", "message": str(e)},
                    },
                )
        except Exception as e:
            log.exception("client handler error")
            with contextlib.suppress(OSError):
                write_frame(
                    conn,
                    {
                        "v": 1,
                        "id": "",
                        "ok": False,
                        "cmd": "",
                        "error": {"code": "internal", "message": str(e)},
                    },
                )
        finally:
            with contextlib.suppress(OSError):
                conn.close()

    def _dispatch(self, req: DaemonRequest) -> DaemonResponse:
        if req.cmd == "ping":
            return DaemonResponse.success(
                req, ResultBody(pid=os.getpid(), provider=self.provider_name)
            )

        if req.cmd == "status":
            return DaemonResponse.success(req, self.status_result())

        if req.cmd == "shutdown":
            # Reply first; stop after short delay so response flushes
            threading.Thread(target=self._delayed_stop, daemon=True).start()
            return DaemonResponse.success(req, ResultBody(pid=os.getpid()))

        if req.cmd == "list_voices":
            try:
                voices = self.provider.list_voices()
                return DaemonResponse.success(req, ResultBody(voices=voices))
            except Exception as e:
                return DaemonResponse.failure(req, "inference_error", str(e))

        if req.cmd in ("speak", "save"):
            if req.provider and req.provider != self.provider_name:
                return DaemonResponse.failure(
                    req,
                    "provider_mismatch",
                    f"You have an active gensay daemon hosting {self.provider_name!r}, but this "
                    f"request asked for {req.provider!r}. In daemon mode the hosted provider "
                    f"wins: drop -p/--provider (or your configured provider default) to use "
                    f"{self.provider_name!r}, or restart the daemon with "
                    f"`gensay daemon restart -p {req.provider}`.",
                )
            if not req.text:
                return DaemonResponse.failure(req, "bad_request", "text is required")
            if req.cmd == "save" and not req.output:
                return DaemonResponse.failure(req, "bad_request", "output is required for save")
            return self._enqueue_job(req)

        return DaemonResponse.failure(req, "bad_request", f"unknown cmd {req.cmd!r}")

    def _enqueue_job(self, req: DaemonRequest) -> DaemonResponse:
        fut: Future = Future()
        self._job_queue.put(_Job(request=req, future=fut))
        timeout = req.timeout_s if req.timeout_s is not None else self.job_timeout_s
        try:
            return fut.result(timeout=timeout)
        except TimeoutError:
            return DaemonResponse.failure(req, "busy_timeout", f"job timed out after {timeout}s")

    def _worker_loop(self) -> None:
        while True:
            job = self._job_queue.get()
            if job is None:
                self._job_queue.task_done()
                break
            try:
                resp = self._run_job(job.request)
                if not job.future.cancelled():
                    job.future.set_result(resp)
            except Exception as e:
                log.exception("job failed")
                if not job.future.cancelled():
                    job.future.set_result(
                        DaemonResponse.failure(job.request, "inference_error", str(e))
                    )
            finally:
                self._job_queue.task_done()

    def _run_job(self, req: DaemonRequest) -> DaemonResponse:
        t0 = time.perf_counter()
        with self._lock:
            self._last_request_at = time.time()

        # Ensure model present (reload after idle-unload)
        if not self._model_loaded and hasattr(self.provider, "warmup"):
            try:
                self.provider.warmup()
                self._model_loaded = True
            except Exception as e:
                return DaemonResponse.failure(req, "not_loaded", str(e))

        voice = req.voice
        rate = req.rate

        try:
            if req.cmd == "speak":
                self.provider.speak(req.text or "", voice=voice, rate=rate)
                elapsed = int((time.perf_counter() - t0) * 1000)
                return DaemonResponse.success(
                    req, ResultBody(elapsed_ms=elapsed, provider=self.provider_name)
                )

            # save
            out = Path(req.output or "")
            fmt = AudioFormat(req.format) if req.format else None
            path = self.provider.save_to_file(
                req.text or "", out, voice=voice, rate=rate, format=fmt
            )
            elapsed = int((time.perf_counter() - t0) * 1000)
            return DaemonResponse.success(
                req,
                ResultBody(
                    elapsed_ms=elapsed,
                    path=str(path),
                    provider=self.provider_name,
                ),
            )
        except Exception as e:
            log.error("inference error: %s\n%s", e, traceback.format_exc())
            return DaemonResponse.failure(req, "inference_error", str(e))

    def _idle_loop(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(timeout=1.0)
            if self._stop.is_set():
                break
            anchor = self._last_request_at or self._started_at
            idle = time.time() - anchor
            # Don't idle-exit/unload while jobs pending
            if self._job_queue.qsize() > 0:
                continue
            if self.idle_exit_s > 0 and idle >= self.idle_exit_s:
                log.info("idle_exit after %.1fs", idle)
                self.stop()
                break
            if (
                self.idle_unload_s > 0
                and idle >= self.idle_unload_s
                and self._model_loaded
                and hasattr(self.provider, "unload")
            ):
                try:
                    self.provider.unload()  # type: ignore[attr-defined]
                    self._model_loaded = False
                    log.info("idle_unload after %.1fs", idle)
                except Exception:
                    log.exception("idle unload failed")

    def _delayed_stop(self) -> None:
        time.sleep(0.05)
        self.stop()

    def _shutdown_internal(self) -> None:
        log.info("daemon shutting down")
        # Stop worker
        self._job_queue.put(None)
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
        if self._sock:
            with contextlib.suppress(OSError):
                self._sock.close()
            self._sock = None
        for path in (self.paths.socket, self.paths.pidfile):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass


def build_provider(provider_name: str, config: TTSConfig | None = None) -> TTSProvider:
    """Construct a provider by name (lazy imports via the registry)."""
    # Registry metadata is cheap; the heavy class is imported only on load().
    from ..providers.registry import SPECS_BY_NAME, names_where

    name = provider_name.lower()
    spec = SPECS_BY_NAME.get(name)
    if spec is None or not spec.daemon_hostable:
        hostable = ", ".join(sorted(names_where(lambda s: s.daemon_hostable)))
        raise ValueError(
            f"daemon only hosts providers with expensive local state "
            f"({hostable}); {provider_name!r} gains nothing from being kept resident"
        )
    return spec.load()(config or TTSConfig())


def run_server(
    provider_name: str,
    *,
    config: TTSConfig | None = None,
    paths: DaemonPaths | None = None,
    preload: bool = True,
    idle_unload_s: float = 0.0,
    idle_exit_s: float = 0.0,
) -> None:
    """Foreground entry: construct provider and run until signal/stop."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [gensay.daemon] %(message)s",
    )
    paths = paths or default_paths()
    provider = build_provider(provider_name, config)
    server = DaemonServer(
        provider,
        provider_name=provider_name,
        paths=paths,
        preload=preload,
        idle_unload_s=idle_unload_s,
        idle_exit_s=idle_exit_s,
    )

    def _handle_signal(signum: int, _frame: Any) -> None:
        log.info("signal %s received", signum)
        server.stop()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    server.start()


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("gensay")
    except Exception:
        return "unknown"
