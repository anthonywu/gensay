"""Shared pipeline for cloud (network API) TTS providers.

Every cloud provider does the same thing: resolve voice/rate/format, build a
cache key, check the cache, synthesize bytes on a miss, cache them, then play
or write them — wrapping any failure so the offline fallback can inspect the
cause chain. ``CloudTTSProvider`` owns that pipeline; concrete providers
implement one hook, :meth:`_prepare`, that returns the provider-specific
cache-key parts and a zero-arg synthesis closure.

Cache-key compatibility: keys are ``sha256("provider|part|part|...")`` with
parts stringified exactly like an f-string would, so providers migrating to
this base keep their existing cache entries.
"""

from __future__ import annotations

import hashlib
import os
from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..cache import TTSCache
from .base import AudioFormat, TTSConfig, TTSProvider
from .playback import play_audio_bytes


@dataclass(frozen=True)
class PreparedSynthesis:
    """Everything the shared pipeline needs for one synthesis request."""

    cache_parts: tuple[Any, ...]
    """Provider-specific cache-key components (text, voice, speed, ...).
    Stringified and joined with ``|`` after the provider's cache namespace."""

    synthesize: Callable[[], bytes]
    """Zero-arg closure performing the network call, returning audio bytes."""

    playback_suffix: str = ".mp3"
    """Temp-file suffix when playing this audio locally."""


class CloudTTSProvider(TTSProvider):
    """Template-method base class for cloud TTS providers.

    Subclasses set :attr:`cache_namespace` and :attr:`display_name`, and
    implement :meth:`_prepare` (and the usual ``list_voices`` /
    ``get_supported_formats``). ``format=None`` in ``_prepare`` means the
    audio is for local playback; providers pick their playback format.
    """

    cache_namespace: str
    """Cache-key prefix, e.g. ``"openai"``. Must never change once shipped."""

    display_name: str
    """Human name used in error messages, e.g. ``"OpenAI"``."""

    def __init__(self, config: TTSConfig | None = None):
        super().__init__(config)
        self._cache = TTSCache(enabled=self.config.cache_enabled)

    # -- hook -------------------------------------------------------------

    @abstractmethod
    def _prepare(
        self,
        text: str,
        voice: str | None,
        rate: int | None,
        format: AudioFormat | None,
    ) -> PreparedSynthesis:
        """Resolve provider-specific parameters for one synthesis request."""

    # -- shared pipeline ---------------------------------------------------

    def speak(self, text: str, voice: str | None = None, rate: int | None = None) -> None:
        """Synthesize (or reuse cached audio) and play locally."""
        # _prepare validates user input (e.g. voice names) — its errors
        # surface unwrapped; only synthesis/playback failures get wrapped.
        prepared = self._prepare(text, voice, rate, format=None)
        try:
            audio_data = self._get_or_synthesize(prepared)
            self.update_progress(0.8, "Playing audio...")
            self._play(audio_data, prepared.playback_suffix)
            self.update_progress(1.0, "Complete")
        except Exception as e:
            raise RuntimeError(f"{self.display_name} TTS failed: {e}") from e

    def save_to_file(
        self,
        text: str,
        output_path: str | Path,
        voice: str | None = None,
        rate: int | None = None,
        format: AudioFormat | None = None,
    ) -> Path:
        """Synthesize (or reuse cached audio) and write to ``output_path``."""
        output_path = Path(output_path)
        format = format or self.config.format or AudioFormat.from_extension(output_path)
        prepared = self._prepare(text, voice, rate, format)
        try:
            audio_data = self._get_or_synthesize(prepared)
            self.update_progress(0.9, "Saving to file...")
            output_path.write_bytes(audio_data)
            self.update_progress(1.0, "Complete")
            return output_path
        except Exception as e:
            raise RuntimeError(f"{self.display_name} TTS failed: {e}") from e

    def _get_or_synthesize(self, prepared: PreparedSynthesis) -> bytes:
        """Cache lookup → synthesis on miss → cache store."""
        cache_key = self._cache_key(*prepared.cache_parts)
        self.update_progress(0.0, "Checking cache...")
        audio_data = self._cache.get(cache_key)
        if audio_data is None:
            self.update_progress(0.2, "Generating speech...")
            audio_data = prepared.synthesize()
            self._cache.put(cache_key, audio_data)
        else:
            self.update_progress(0.5, "Using cached audio...")
        return audio_data

    def _cache_key(self, *parts: Any) -> str:
        """``sha256("namespace|part|part|...")`` with f-string stringification."""
        data = "|".join([self.cache_namespace, *(f"{p}" for p in parts)])
        return hashlib.sha256(data.encode()).hexdigest()

    def _play(self, audio_data: bytes, suffix: str) -> None:
        """Play synthesized bytes locally. Override for SDK-native playback."""
        play_audio_bytes(audio_data, suffix)

    # -- shared helpers ----------------------------------------------------

    @staticmethod
    def resolve_api_key(
        env_var: str,
        config: TTSConfig | None,
        *,
        display_name: str,
        config_hint: str = "",
    ) -> str:
        """API key resolution shared by key-based cloud providers.

        Precedence: environment variable, then ``config.extra['api_key']``
        (filled from the OS keychain by the CLI). Raises ``ValueError`` with
        a setup hint when neither is present.
        """
        api_key = os.getenv(env_var) or (config.extra.get("api_key") if config else None)
        if not api_key:
            hint = f" {config_hint}" if config_hint else ""
            raise ValueError(
                f"{display_name} API key not found. Please set {env_var} "
                f"environment variable or pass it in config.extra['api_key']{hint}"
            )
        return api_key
