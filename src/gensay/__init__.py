"""gensay - A multi-provider TTS tool compatible with macOS say command."""

import warnings

# Suppress pkg_resources deprecation warning from perth package
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message=".*pkg_resources is deprecated.*",
    module="perth.perth_net",
)

# Suppress diffusers LoRACompatibleLinear deprecation warning
warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    message=".*LoRACompatibleLinear.*is deprecated.*",
    module="diffusers.models.lora",
)

# Suppress torch.backends.cuda.sdp_kernel deprecation warning
warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    message=".*torch.backends.cuda.sdp_kernel.*is deprecated.*",
    module="contextlib",
)

# Suppress SDPA attention warnping
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message=".*sdpa.*attention does not support.*output_attentions.*",
)

from .cache import TTSCache  # noqa: E402
from .providers import (  # noqa: E402
    AmazonPollyProvider,
    AudioFormat,
    ChatterboxProvider,
    ElevenLabsProvider,
    MacOSSayProvider,
    MockProvider,
    OpenAIProvider,
    ProgressCallback,
    TTSConfig,
    TTSProvider,
)
from .text_chunker import TextChunker, chunk_text_for_tts  # noqa: E402

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
    "TTSCache",
    "TextChunker",
    "chunk_text_for_tts",
]
