"""Offline resilience: transparently fall back to macOS `say` when the
network is unreachable (e.g. laptop offline with a cloud provider default).

Detection walks the exception chain (providers wrap with ``raise ... from e``)
looking for OS-level network errnos or well-known SDK network exception names.
SSL/cert errors are intentionally NOT network errors (captive portals / MITM
would otherwise be silently masked).
"""

from __future__ import annotations

import errno
import socket
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .providers.base import AudioFormat, TTSProvider

# BSD errnos that mean "the network is down/unreachable"
_NETWORK_ERRNOS = frozenset(
    n
    for n in (
        getattr(errno, name, None)
        for name in (
            "ENETDOWN",
            "ENETUNREACH",
            "EHOSTDOWN",
            "EHOSTUNREACH",
            "ECONNABORTED",
            "ECONNRESET",
            "ECONNREFUSED",
            "ETIMEDOUT",
            "ENONET",
            "EPIPE",
        )
    )
    if n is not None and n != 0
)

# SDK network exceptions matched by class name, avoiding hard imports:
# httpx.httpcore ConnectError, urllib3 NameResolutionError / NewConnectionError,
# botocore EndpointConnectionError
_NETWORK_ERROR_NAMES = frozenset(
    {
        "ConnectError",
        "ConnectTimeout",
        "NetworkError",
        "NameResolutionError",
        "NewConnectionError",
        "EndpointConnectionError",
    }
)


def is_network_error(exc: BaseException, *, max_depth: int = 10) -> bool:
    """True if ``exc`` (or its cause chain) indicates the network is unreachable."""
    seen: set[int] = set()
    cur: BaseException | None = exc
    for _ in range(max_depth):
        if cur is None or id(cur) in seen:
            break
        seen.add(id(cur))
        if isinstance(cur, (ConnectionError, TimeoutError, socket.gaierror)):
            return True
        if isinstance(cur, OSError) and cur.errno in _NETWORK_ERRNOS:
            return True
        if type(cur).__name__ in _NETWORK_ERROR_NAMES:
            return True
        cur = cur.__cause__ or cur.__context__
    return False


class NetworkFallbackProvider(TTSProvider):
    """Delegate to ``primary``; on network-unreachable errors, retry with a local fallback.

    The fallback is created lazily (only on first network failure) and receives a
    voice-less config — cloud voice names (e.g. Matilda) are not valid for `say`.
    """

    def __init__(
        self,
        primary: TTSProvider,
        fallback_factory: Callable[[], TTSProvider],
        *,
        primary_name: str | None = None,
    ):
        super().__init__(primary.config)
        self._primary = primary
        self._fallback_factory = fallback_factory
        self._fallback: TTSProvider | None = None
        self._primary_name = primary_name or type(primary).__name__

    def _get_fallback(self) -> TTSProvider:
        if self._fallback is None:
            print(
                f"Warning: {self._primary_name} unreachable (offline?) — "
                "falling back to macos provider",
                file=sys.stderr,
            )
            self._fallback = self._fallback_factory()
        return self._fallback

    def speak(self, text: str, voice: str | None = None, rate: int | None = None) -> None:
        try:
            self._primary.speak(text, voice, rate)
        except Exception as e:
            if not is_network_error(e):
                raise
            self._get_fallback().speak(text, None, rate)

    def save_to_file(
        self,
        text: str,
        output_path: str | Path,
        voice: str | None = None,
        rate: int | None = None,
        format: AudioFormat | None = None,
    ) -> Path:
        try:
            return self._primary.save_to_file(text, output_path, voice, rate, format)
        except Exception as e:
            if not is_network_error(e):
                raise
            return self._get_fallback().save_to_file(text, output_path, None, rate, format)

    def list_voices(self) -> list[dict[str, Any]]:
        return self._primary.list_voices()

    def list_models(self) -> list[dict[str, Any]]:
        return self._primary.list_models()

    def get_supported_formats(self) -> list[AudioFormat]:
        return self._primary.get_supported_formats()

    @property
    def display_name(self) -> str | None:
        """Voice/model listings should show the wrapped provider, not the wrapper."""
        return getattr(self._primary, "display_name", None)

    @property
    def cache_namespace(self) -> str | None:
        return getattr(self._primary, "cache_namespace", None)
