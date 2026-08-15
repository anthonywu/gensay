"""Tests for the public plugin API facade (gensay.plugin)."""

import inspect

from gensay import plugin


def test_all_names_resolve():
    for name in plugin.__all__:
        assert getattr(plugin, name) is not None


def test_facade_matches_internal_definitions():
    """The facade must re-export the same objects the registry/pipeline use,
    so isinstance checks across plugin and core agree."""
    from gensay.providers.base import TTSProvider
    from gensay.providers.cloud import CloudTTSProvider, PreparedSynthesis
    from gensay.providers.registry import ENTRY_POINT_GROUP, ProviderSpec

    assert plugin.ProviderSpec is ProviderSpec
    assert plugin.TTSProvider is TTSProvider
    assert plugin.CloudTTSProvider is CloudTTSProvider
    assert plugin.PreparedSynthesis is PreparedSynthesis
    assert plugin.ENTRY_POINT_GROUP is ENTRY_POINT_GROUP


def test_facade_is_import_cheap():
    """Importing gensay.plugin must not pull in provider implementation
    modules (fresh subprocess: this process has already imported them)."""
    import subprocess
    import sys

    code = (
        "import sys; import gensay.plugin; "
        "heavy = ["
        "'gensay.providers.chatterbox', 'gensay.providers.openai', "
        "'gensay.providers.elevenlabs', 'gensay.providers.amazon_polly', "
        "'gensay.providers.deepgram']; "
        "loaded = [m for m in heavy if m in sys.modules]; "
        "sys.exit(f'imported {loaded}' if loaded else 0)"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_spec_signature_stable():
    """Plugin authors construct ProviderSpec by keyword; catch accidental
    parameter renames, which would break every published plugin."""
    params = set(inspect.signature(plugin.ProviderSpec).parameters)
    assert {
        "name",
        "class_name",
        "module",
        "kind",
        "warm_eligible",
        "daemon_hostable",
        "env_api_key",
        "config_keys",
        "install_extra",
    } <= params
