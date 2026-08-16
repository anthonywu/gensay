"""Public API for gensay provider plugins.

Everything a third-party provider package needs, importable from one stable
module. Internal module paths (``gensay.providers.registry`` etc.) may move
between releases; this facade will not.

A plugin is a normal Python package that:

1. Declares an entry point in the ``gensay.providers`` group pointing at a
   ``ProviderSpec`` instance::

       [project.entry-points."gensay.providers"]
       acme = "acme_tts:GENSAY_PROVIDER_SPEC"

2. Keeps the entry-point module import-cheap (just the spec; no SDK imports).
   The provider class named by the spec is imported lazily, only when the
   user selects that provider.

3. Implements the provider class:

   - Cloud/network backends: subclass :class:`CloudTTSProvider` and implement
     ``_prepare`` (returning a :class:`PreparedSynthesis`), ``list_voices``,
     and ``get_supported_formats``. Caching, playback, progress reporting,
     and error wrapping are inherited. Optionally set
     ``PreparedSynthesis.synthesize_stream`` (a zero-arg closure yielding
     audio chunks) to get streaming playback — audio starts on the first
     chunk when a stdin-capable player (ffplay/mpv) is installed.
   - Anything else (local models, system engines): subclass
     :class:`TTSProvider` and implement its abstract methods directly.

See ``examples/gensay-plugin-example`` in the gensay repository for a
complete installable plugin.
"""

from .providers.base import (
    AudioFormat,
    ProgressCallback,
    TTSConfig,
    TTSProvider,
)
from .providers.cloud import CloudTTSProvider, PreparedSynthesis
from .providers.playback import play_audio_bytes
from .providers.registry import ENTRY_POINT_GROUP, ProviderKind, ProviderSpec

__all__ = [
    "ENTRY_POINT_GROUP",
    "AudioFormat",
    "CloudTTSProvider",
    "PreparedSynthesis",
    "ProgressCallback",
    "ProviderKind",
    "ProviderSpec",
    "TTSConfig",
    "TTSProvider",
    "play_audio_bytes",
]
