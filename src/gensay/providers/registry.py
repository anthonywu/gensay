"""Provider registry: the single source of truth for provider metadata.

Everything the rest of gensay needs to know *about* a provider — its CLI
name, where its class lives, whether it is cloud or local, whether the warm
daemon may host it, its API-key env var, and its per-user config keys —
lives here as cheap data. The heavy provider class is imported only when
actually instantiated (``ProviderSpec.load``), preserving lazy imports.

Adding a provider = adding one ``ProviderSpec`` here plus the implementation
module. CLI choices, offline-fallback eligibility, daemon hosting, and
``gensay config`` keys are all derived from this table.

Third-party plugins: packages may register additional providers via the
``gensay.providers`` entry-point group. Each entry point must resolve to a
``ProviderSpec`` instance (keep that module import-cheap; the provider class
itself stays lazy behind ``ProviderSpec.load``)::

    # pyproject.toml of a plugin package
    [project.entry-points."gensay.providers"]
    acme = "acme_tts:GENSAY_PROVIDER_SPEC"

Builtin names always win; malformed or colliding plugin specs are skipped
with a warning rather than breaking the CLI.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from importlib import import_module
from typing import Literal

ProviderKind = Literal["cloud", "local", "system", "test"]

ENTRY_POINT_GROUP = "gensay.providers"

_VALID_KINDS: tuple[ProviderKind, ...] = ("cloud", "local", "system", "test")


@dataclass(frozen=True)
class ProviderSpec:
    """Cheap, import-safe metadata for one TTS provider."""

    name: str
    """CLI/config name, e.g. ``openai``."""

    class_name: str
    """Provider class name, e.g. ``OpenAIProvider``."""

    module: str
    """Module containing the class, e.g. ``gensay.providers.openai``."""

    kind: ProviderKind
    """``cloud`` (network API, gets offline fallback), ``local`` (on-device
    model), ``system`` (OS-provided), or ``test``."""

    warm_eligible: bool = False
    """Expensive process-local state — prefer the warm daemon when running."""

    daemon_hostable: bool = False
    """The daemon may host this provider (warm-eligible ones, plus mock)."""

    env_api_key: str | None = None
    """Environment variable holding the API key, if the provider uses one."""

    config_keys: tuple[tuple[str, type], ...] = ()
    """Per-user config keys (sub-key, type) exposed as ``<name>.<sub-key>``
    via ``gensay config``; ``api_key`` sub-keys are stored in the OS keychain."""

    install_extra: str | None = None
    """Optional-dependency extra needed for this provider, if any."""

    def load(self) -> type:
        """Import and return the provider class (the only non-cheap call)."""
        return getattr(import_module(self.module), self.class_name)


BUILTIN_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        name="chatterbox",
        class_name="ChatterboxProvider",
        module="gensay.providers.chatterbox",
        kind="local",
        warm_eligible=True,
        daemon_hostable=True,
        install_extra="gensay[chatterbox]",
    ),
    ProviderSpec(
        name="deepgram",
        class_name="DeepgramProvider",
        module="gensay.providers.deepgram",
        kind="cloud",
        env_api_key="DEEPGRAM_API_KEY",
        config_keys=(("api_key", str), ("model", str)),
    ),
    ProviderSpec(
        name="elevenlabs",
        class_name="ElevenLabsProvider",
        module="gensay.providers.elevenlabs",
        kind="cloud",
        env_api_key="ELEVENLABS_API_KEY",
        config_keys=(("api_key", str), ("model", str)),
        install_extra="gensay[elevenlabs]",
    ),
    ProviderSpec(
        name="macos",
        class_name="MacOSSayProvider",
        module="gensay.providers.macos_say",
        kind="system",
    ),
    ProviderSpec(
        name="mock",
        class_name="MockProvider",
        module="gensay.providers.mock",
        kind="test",
        daemon_hostable=True,
    ),
    ProviderSpec(
        name="openai",
        class_name="OpenAIProvider",
        module="gensay.providers.openai",
        kind="cloud",
        env_api_key="OPENAI_API_KEY",
        config_keys=(("api_key", str), ("model", str)),
    ),
    ProviderSpec(
        name="polly",
        class_name="AmazonPollyProvider",
        module="gensay.providers.amazon_polly",
        kind="cloud",
        # Auth via the standard AWS credential chain (env/aws login/IAM),
        # not a gensay-managed api_key.
        config_keys=(("engine", str), ("aws_profile", str), ("aws_region", str)),
    ),
)


def _plugin_warning(message: str) -> None:
    print(f"Warning: {message}", file=sys.stderr)


def discover_plugin_specs(entry_points_iter=None) -> tuple[ProviderSpec, ...]:
    """Load third-party ProviderSpecs from the ``gensay.providers`` group.

    Skips (with a stderr warning) entry points that fail to import, don't
    resolve to a ``ProviderSpec``, carry an invalid kind, or collide with a
    builtin or earlier plugin name. Never raises: a broken plugin must not
    take down the CLI.
    """
    if entry_points_iter is None:
        try:
            from importlib.metadata import entry_points

            entry_points_iter = entry_points(group=ENTRY_POINT_GROUP)
        except Exception as e:  # pragma: no cover - defensive
            _plugin_warning(f"gensay provider plugin discovery failed: {e}")
            return ()

    out: list[ProviderSpec] = []
    seen = {spec.name for spec in BUILTIN_SPECS}
    for ep in entry_points_iter:
        try:
            spec = ep.load()
        except Exception as e:
            _plugin_warning(f"could not load gensay provider plugin {ep.name!r}: {e}")
            continue
        if not isinstance(spec, ProviderSpec):
            _plugin_warning(
                f"gensay provider plugin {ep.name!r} must resolve to a ProviderSpec, "
                f"got {type(spec).__name__}; skipping"
            )
            continue
        if spec.kind not in _VALID_KINDS:
            _plugin_warning(
                f"gensay provider plugin {spec.name!r} has invalid kind {spec.kind!r}; skipping"
            )
            continue
        if spec.name in seen:
            _plugin_warning(
                f"gensay provider plugin name {spec.name!r} collides with an existing "
                "provider; skipping"
            )
            continue
        seen.add(spec.name)
        out.append(spec)
    return tuple(out)


SPECS: tuple[ProviderSpec, ...] = (*BUILTIN_SPECS, *discover_plugin_specs())

SPECS_BY_NAME: dict[str, ProviderSpec] = {spec.name: spec for spec in SPECS}


def provider_names() -> list[str]:
    """All provider names, sorted (CLI choices)."""
    return sorted(SPECS_BY_NAME)


def names_where(predicate) -> frozenset[str]:
    """Names of providers matching a predicate over ProviderSpec."""
    return frozenset(spec.name for spec in SPECS if predicate(spec))


def load_provider_class(name: str) -> type:
    """Import and return the provider class for a registered name."""
    try:
        spec = SPECS_BY_NAME[name]
    except KeyError:
        raise KeyError(f"Unknown provider {name!r}. Known: {', '.join(provider_names())}") from None
    return spec.load()


def load_all_provider_classes() -> dict[str, type]:
    """Import every provider class; name → class (imports all modules)."""
    return {spec.name: spec.load() for spec in SPECS}


def provider_config_key_types() -> dict[str, type]:
    """Dotted ``<provider>.<key>`` → value type for the user config store."""
    return {
        f"{spec.name}.{sub_key}": value_type
        for spec in SPECS
        for sub_key, value_type in spec.config_keys
    }
