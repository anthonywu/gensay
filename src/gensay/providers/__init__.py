"""TTS Provider implementations for gensay.

Uses lazy imports to avoid loading heavy provider dependencies until needed.
"""

from .base import AudioFormat, ProgressCallback, TTSConfig, TTSProvider
from .registry import SPECS, SPECS_BY_NAME, ProviderSpec

_CLASS_NAME_TO_SPEC = {spec.class_name: spec for spec in SPECS}


def __getattr__(name: str):
    """Lazy import provider classes to avoid loading heavy dependencies."""
    if spec := _CLASS_NAME_TO_SPEC.get(name):
        return spec.load()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "TTSProvider",
    "TTSConfig",
    "AudioFormat",
    "ProgressCallback",
    "ProviderSpec",
    "SPECS",
    "SPECS_BY_NAME",
    *sorted(_CLASS_NAME_TO_SPEC),
]
