"""Tests for the provider registry (providers/registry.py)."""

from pathlib import Path

import pytest

from gensay.providers import registry
from gensay.providers.registry import (
    SPECS,
    SPECS_BY_NAME,
    ProviderSpec,
    load_provider_class,
    names_where,
    provider_config_key_types,
    provider_names,
)


class TestSpecsTable:
    def test_names_are_unique(self):
        names = [spec.name for spec in SPECS]
        assert len(names) == len(set(names))

    def test_by_name_index_matches_table(self):
        expected = {spec.name: spec for spec in SPECS}
        assert expected == SPECS_BY_NAME

    def test_expected_providers_registered(self):
        assert set(provider_names()) == {
            "chatterbox",
            "deepgram",
            "elevenlabs",
            "macos",
            "mock",
            "openai",
            "polly",
        }

    def test_provider_names_sorted(self):
        assert provider_names() == sorted(provider_names())

    def test_specs_are_frozen(self):
        with pytest.raises(AttributeError):
            SPECS_BY_NAME["mock"].name = "other"  # type: ignore[misc]

    def test_cloud_providers(self):
        assert names_where(lambda s: s.kind == "cloud") == {
            "deepgram",
            "elevenlabs",
            "openai",
            "polly",
        }

    def test_daemon_hostable_includes_warm_eligible(self):
        hostable = names_where(lambda s: s.daemon_hostable)
        warm = names_where(lambda s: s.warm_eligible)
        assert warm <= hostable

    def test_api_key_cloud_providers_expose_env_and_config_key(self):
        for spec in SPECS:
            if spec.env_api_key is not None:
                assert spec.kind == "cloud"
                sub_keys = {sub for sub, _ in spec.config_keys}
                assert "api_key" in sub_keys, spec.name


class TestLazyLoading:
    def test_registry_import_does_not_import_provider_modules(self):
        # Heavy provider modules must not be imported as a side effect of
        # importing the registry (they may be missing optional deps).
        # Direct check: the registry module itself has no provider imports.
        import gensay.providers.registry as reg_module

        assert reg_module.__file__ is not None
        source = Path(reg_module.__file__).read_text(encoding="utf-8")
        for spec in SPECS:
            assert f"from {spec.module}" not in source
            assert f"import {spec.module}" not in source

    def test_load_returns_class_with_matching_name(self):
        cls = load_provider_class("mock")
        assert cls.__name__ == "MockProvider"

    def test_load_unknown_name_raises_keyerror_listing_known(self):
        with pytest.raises(KeyError, match="Unknown provider 'nope'"):
            load_provider_class("nope")

    def test_spec_load_is_equivalent(self):
        spec = SPECS_BY_NAME["mock"]
        assert spec.load() is load_provider_class("mock")


class TestConfigKeyDerivation:
    def test_dotted_keys_shape(self):
        keys = provider_config_key_types()
        for dotted, typ in keys.items():
            provider, _, sub = dotted.partition(".")
            assert provider in SPECS_BY_NAME
            assert sub
            assert isinstance(typ, type)

    def test_known_provider_keys_present(self):
        keys = provider_config_key_types()
        assert keys["openai.api_key"] is str
        assert keys["openai.model"] is str
        assert keys["deepgram.api_key"] is str
        assert keys["elevenlabs.model"] is str
        # Polly has no api_key (AWS credential chain) but exposes tuning keys
        assert keys["polly.engine"] is str
        assert keys["polly.aws_profile"] is str
        assert keys["polly.aws_region"] is str
        assert "polly.api_key" not in keys


class TestNamesWhere:
    def test_predicate_filters(self):
        assert names_where(lambda s: s.name == "mock") == {"mock"}
        assert names_where(lambda s: False) == frozenset()

    def test_returns_frozenset(self):
        assert isinstance(names_where(lambda s: True), frozenset)


def test_spec_load_helper_uses_module_and_class_name():
    spec = ProviderSpec(
        name="fake",
        class_name="MockProvider",
        module="gensay.providers.mock",
        kind="test",
    )
    assert spec.load().__name__ == "MockProvider"


def test_registry_derivations_match_cli_surface():
    """main.py derives its provider surface from the registry."""
    from gensay import main as gensay_main

    assert set(gensay_main.CLOUD_PROVIDERS) == registry.names_where(lambda s: s.kind == "cloud")
