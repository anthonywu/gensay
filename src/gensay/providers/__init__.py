"""TTS Provider implementations for gensay.

Uses lazy imports to avoid loading heavy provider dependencies until needed.
"""

from .base import AudioFormat, ProgressCallback, TTSConfig, TTSProvider


def __getattr__(name: str):
    """Lazy import provider classes to avoid loading heavy dependencies."""
    if name == "ChatterboxProvider":
        from .chatterbox import ChatterboxProvider

        return ChatterboxProvider
    elif name == "ElevenLabsProvider":
        from .elevenlabs import ElevenLabsProvider

        return ElevenLabsProvider
    elif name == "MacOSSayProvider":
        from .macos_say import MacOSSayProvider

        return MacOSSayProvider
    elif name == "MockProvider":
        from .mock import MockProvider

        return MockProvider
    elif name == "OpenAIProvider":
        from .openai import OpenAIProvider

        return OpenAIProvider
    elif name == "AmazonPollyProvider":
        from .amazon_polly import AmazonPollyProvider

        return AmazonPollyProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "TTSProvider",
    "TTSConfig",
    "AudioFormat",
    "ProgressCallback",
    "ChatterboxProvider",
    "MacOSSayProvider",
    "MockProvider",
    "OpenAIProvider",
    "ElevenLabsProvider",
    "AmazonPollyProvider",
]
