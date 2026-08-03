"""Length-prefixed JSON protocol for gensay daemon IPC."""

from __future__ import annotations

import json
import struct
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, BinaryIO, Literal

PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 1 * 1024 * 1024  # 1 MiB
HEADER = struct.Struct("!I")

Command = Literal["speak", "save", "ping", "status", "shutdown", "list_voices"]


class ProtocolError(ValueError):
    """Invalid frame or message body."""


@dataclass
class ErrorBody:
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ErrorBody:
        return cls(code=str(data.get("code", "error")), message=str(data.get("message", "")))


@dataclass
class ResultBody:
    """Flexible result payload; fields used depend on command."""

    cached: bool | None = None
    elapsed_ms: int | None = None
    path: str | None = None
    voices: list[dict[str, Any]] | None = None
    # status fields
    pid: int | None = None
    uptime_s: float | None = None
    provider: str | None = None
    model_loaded: bool | None = None
    device: str | None = None
    queue_depth: int | None = None
    last_request_at: float | None = None
    idle_s: float | None = None
    version: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        extra = d.pop("extra", {}) or {}
        # Drop Nones for compact wire format
        out = {k: v for k, v in d.items() if v is not None}
        out.update(extra)
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ResultBody:
        if not data:
            return cls()
        known = {
            "cached",
            "elapsed_ms",
            "path",
            "voices",
            "pid",
            "uptime_s",
            "provider",
            "model_loaded",
            "device",
            "queue_depth",
            "last_request_at",
            "idle_s",
            "version",
        }
        kwargs = {k: data[k] for k in known if k in data}
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(**kwargs, extra=extra)


@dataclass
class DaemonRequest:
    cmd: Command
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    v: int = PROTOCOL_VERSION
    text: str | None = None
    voice: str | None = None
    rate: int | None = None
    output: str | None = None
    format: str | None = None
    no_cache: bool = False
    timeout_s: float | None = None
    provider: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "v": self.v,
            "id": self.id,
            "cmd": self.cmd,
            "no_cache": self.no_cache,
        }
        for key in ("text", "voice", "rate", "output", "format", "timeout_s", "provider"):
            if (val := getattr(self, key)) is not None:
                d[key] = val
        return d

    def to_bytes(self) -> bytes:
        return encode_frame(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DaemonRequest:
        if not isinstance(data, dict):
            raise ProtocolError("request body must be an object")
        cmd = data.get("cmd")
        if cmd not in ("speak", "save", "ping", "status", "shutdown", "list_voices"):
            raise ProtocolError(f"invalid cmd: {cmd!r}")
        return cls(
            cmd=cmd,
            id=str(data.get("id") or uuid.uuid4().hex),
            v=int(data.get("v", PROTOCOL_VERSION)),
            text=data.get("text"),
            voice=data.get("voice"),
            rate=data.get("rate"),
            output=data.get("output"),
            format=data.get("format"),
            no_cache=bool(data.get("no_cache", False)),
            timeout_s=data.get("timeout_s"),
            provider=data.get("provider"),
        )


@dataclass
class DaemonResponse:
    id: str
    ok: bool
    cmd: str
    v: int = PROTOCOL_VERSION
    result: ResultBody | None = None
    error: ErrorBody | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "v": self.v,
            "id": self.id,
            "ok": self.ok,
            "cmd": self.cmd,
        }
        if self.result is not None:
            d["result"] = self.result.to_dict()
        if self.error is not None:
            d["error"] = self.error.to_dict()
        return d

    def to_bytes(self) -> bytes:
        return encode_frame(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DaemonResponse:
        if not isinstance(data, dict):
            raise ProtocolError("response body must be an object")
        err = data.get("error")
        return cls(
            id=str(data.get("id", "")),
            ok=bool(data.get("ok")),
            cmd=str(data.get("cmd", "")),
            v=int(data.get("v", PROTOCOL_VERSION)),
            result=ResultBody.from_dict(data.get("result"))
            if data.get("result") is not None
            else None,
            error=ErrorBody.from_dict(err) if isinstance(err, dict) else None,
        )

    @classmethod
    def success(cls, req: DaemonRequest, result: ResultBody | None = None) -> DaemonResponse:
        return cls(id=req.id, ok=True, cmd=req.cmd, result=result or ResultBody())

    @classmethod
    def failure(cls, req: DaemonRequest, code: str, message: str) -> DaemonResponse:
        return cls(
            id=req.id,
            ok=False,
            cmd=req.cmd,
            error=ErrorBody(code=code, message=message),
        )


def encode_frame(obj: dict[str, Any]) -> bytes:
    body = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_FRAME_BYTES:
        raise ProtocolError(f"frame too large: {len(body)} > {MAX_FRAME_BYTES}")
    return HEADER.pack(len(body)) + body


def decode_frame(data: bytes) -> dict[str, Any]:
    if len(data) < HEADER.size:
        raise ProtocolError("short header")
    (length,) = HEADER.unpack_from(data)
    if length > MAX_FRAME_BYTES:
        raise ProtocolError(f"frame length {length} exceeds max {MAX_FRAME_BYTES}")
    body = data[HEADER.size : HEADER.size + length]
    if len(body) != length:
        raise ProtocolError("incomplete frame body")
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ProtocolError(f"invalid json: {e}") from e
    if not isinstance(parsed, dict):
        raise ProtocolError("json root must be object")
    return parsed


def read_frame(sock: BinaryIO | Any, max_bytes: int = MAX_FRAME_BYTES) -> dict[str, Any]:
    """Read one length-prefixed JSON frame from a socket/file-like object."""
    header = _recv_exact(sock, HEADER.size)
    (length,) = HEADER.unpack(header)
    if length > max_bytes:
        raise ProtocolError(f"frame length {length} exceeds max {max_bytes}")
    body = _recv_exact(sock, length)
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ProtocolError(f"invalid json: {e}") from e
    if not isinstance(parsed, dict):
        raise ProtocolError("json root must be object")
    return parsed


def write_frame(sock: BinaryIO | Any, obj: dict[str, Any]) -> None:
    data = encode_frame(obj)
    sock.sendall(data)


def _recv_exact(sock: Any, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ProtocolError("connection closed while reading frame")
        buf.extend(chunk)
    return bytes(buf)
