"""Warm inference daemon: keep TTS providers loaded across ad-hoc CLI calls."""

from .client import DaemonClient, DaemonClientError, DaemonNotRunning
from .paths import DaemonPaths, default_paths
from .protocol import DaemonRequest, DaemonResponse, ErrorBody, ResultBody

__all__ = [
    "DaemonClient",
    "DaemonClientError",
    "DaemonNotRunning",
    "DaemonPaths",
    "DaemonRequest",
    "DaemonResponse",
    "ErrorBody",
    "ResultBody",
    "default_paths",
]
