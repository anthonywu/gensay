"""Unit tests for daemon wire protocol."""

import json
import struct

import pytest

from gensay.daemon.protocol import (
    HEADER,
    MAX_FRAME_BYTES,
    DaemonRequest,
    DaemonResponse,
    ProtocolError,
    ResultBody,
    decode_frame,
    encode_frame,
)


def test_encode_decode_roundtrip():
    obj = {"v": 1, "id": "abc", "cmd": "ping"}
    frame = encode_frame(obj)
    assert frame[:4] == HEADER.pack(len(frame) - 4)
    assert decode_frame(frame) == obj


def test_request_to_from_dict():
    req = DaemonRequest(cmd="speak", text="hello", voice="v1", rate=160)
    restored = DaemonRequest.from_dict(req.to_dict())
    assert restored.cmd == "speak"
    assert restored.text == "hello"
    assert restored.voice == "v1"
    assert restored.rate == 160
    assert restored.id == req.id


def test_response_success_failure():
    req = DaemonRequest(cmd="ping")
    ok = DaemonResponse.success(req, ResultBody(pid=1))
    assert ok.ok
    assert ok.result is not None
    assert ok.result.pid == 1

    bad = DaemonResponse.failure(req, "busy_timeout", "too slow")
    assert not bad.ok
    assert bad.error is not None
    assert bad.error.code == "busy_timeout"


def test_invalid_cmd():
    with pytest.raises(ProtocolError):
        DaemonRequest.from_dict({"cmd": "explode"})


def test_frame_too_large():
    huge = {"x": "y" * (MAX_FRAME_BYTES + 10)}
    with pytest.raises(ProtocolError):
        encode_frame(huge)


def test_decode_rejects_non_object():
    body = json.dumps([1, 2, 3]).encode()
    frame = struct.pack("!I", len(body)) + body
    with pytest.raises(ProtocolError):
        decode_frame(frame)


def test_result_body_drops_nones():
    r = ResultBody(pid=7, provider="mock")
    d = r.to_dict()
    assert d == {"pid": 7, "provider": "mock"} or (
        d["pid"] == 7 and d["provider"] == "mock" and "elapsed_ms" not in d
    )
