"""gensay-tone: example gensay provider plugin.

This module is the entry-point target, so it must stay import-cheap: just
the ProviderSpec. The provider class lives in ``gensay_tone.provider`` and
is imported lazily by gensay only when the user selects ``-p tone``.
"""

from gensay.plugin import ProviderSpec

GENSAY_PROVIDER_SPEC = ProviderSpec(
    name="tone",
    class_name="ToneProvider",
    module="gensay_tone.provider",
    kind="local",
)
