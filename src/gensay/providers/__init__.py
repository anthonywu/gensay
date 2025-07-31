"""TTS Provider implementations for gensay."""

from .amazon_polly import AmazonPollyProvider
from .base import AudioFormat, ProgressCallback, TTSConfig, TTSProvider
from .chatterbox import ChatterboxProvider
from .elevenlabs import ElevenLabsProvider
from .macos_say import MacOSSayProvider
from .mock import MockProvider
from .openai import OpenAIProvider

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
