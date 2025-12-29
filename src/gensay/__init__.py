"""gensay - A multi-provider TTS tool compatible with macOS say command."""

import os
import warnings

# Disable tokenizers parallelism to avoid fork warnings, unless user set it
if "TOKENIZERS_PARALLELISM" not in os.environ:
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

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

# Import lightweight base types only
from .cache import TTSCache  # noqa: E402
from .providers import AudioFormat, ProgressCallback, TTSConfig, TTSProvider  # noqa: E402
from .text_chunker import TextChunker, chunk_text_for_tts  # noqa: E402

# Provider classes are lazy-loaded via __getattr__ to avoid loading heavy dependencies
_PROVIDER_CLASSES = {
    "AmazonPollyProvider",
    "ChatterboxProvider",
    "ElevenLabsProvider",
    "MacOSSayProvider",
    "MockProvider",
    "OpenAIProvider",
}


def __getattr__(name: str):
    """Lazy import provider classes to avoid always loading heavy dependencies for all provider types."""
    if name in _PROVIDER_CLASSES:
        import importlib

        module = importlib.import_module(".providers", __package__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AmazonPollyProvider",
    "AudioFormat",
    "ChatterboxProvider",
    "ElevenLabsProvider",
    "MacOSSayProvider",
    "MockProvider",
    "OpenAIProvider",
    "ProgressCallback",
    "TTSCache",
    "TTSConfig",
    "TTSProvider",
    "TextChunker",
    "chunk_text_for_tts",
]
