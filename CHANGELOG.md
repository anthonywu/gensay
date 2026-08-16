# Changelog

Notable user-facing changes to gensay. Follows [Keep a Changelog](https://keepachangelog.com/) loosely; versions follow [SemVer](https://semver.org/).

## 0.7.0 — 2026-08-15

Provider cleanup release: every cloud provider now shares one pipeline, the
provider system is a plugin model open to third-party packages, and secrets
no longer need to touch your shell history.

### Added

- **Third-party provider plugins.** Any installed package can add a TTS
  provider via the `gensay.providers` entry-point group. Plugins appear in
  `--provider` choices and `gensay config keys` automatically; a broken or
  name-colliding plugin is skipped with a warning instead of breaking the
  CLI. See "Provider plugins" in [USAGE.md](USAGE.md).
- **Stable plugin API: `gensay.plugin`.** Plugin authors import
  `ProviderSpec`, `TTSProvider`, `CloudTTSProvider`, `PreparedSynthesis`,
  `TTSConfig`, and `AudioFormat` from one supported module instead of
  internal paths.
- **Working example plugin.** [`examples/gensay-plugin-example`](examples/gensay-plugin-example/)
  is a complete installable provider (`gensay -p tone`) that beeps text as
  sine-wave tones, offline, stdlib-only.
- **Hidden secret prompt.** `gensay config set openai.api_key` (value
  omitted) now prompts with hidden input, so API keys stay out of shell
  history. Works for every `*.api_key` key.
- **`openai.api_key` config key** stored in the OS keychain, like the other
  cloud providers.
- **Polly config keys.** `polly.engine`, `polly.aws_profile`, and
  `polly.aws_region` are settable via `gensay config set`.
- **`gensay[keychain]` extra** so keychain-backed `api_key` storage installs
  cleanly where the `keyring` dependency is not already present.
- **Per-provider documentation.** [USAGE.md](USAGE.md) has a hero section
  for each provider (OpenAI, Deepgram, ElevenLabs, Amazon Polly, macOS,
  mock): setup, credential storage, voice/rate/format flags, and defaults.
- **`-m`/`--model` flag.** One-off model override per invocation, e.g.
  `gensay -p openai -m gpt-4o-mini-tts "..."`; beats the stored
  `<provider>.model` default. Providers without a model setting warn on
  stderr and ignore the flag instead of silently accepting it.
- **Model listings.** `gensay -p <provider> -v '?'` shows a Models section
  for providers with selectable models (OpenAI, ElevenLabs), starring the
  currently configured one. ElevenLabs models (`eleven_v3`,
  `eleven_multilingual_v2`, `eleven_flash_v2_5`, ...) are listed offline.
- **JSON voice listings.** `gensay -v '?' --json` prints a machine-readable
  `{provider, voices, models}` payload. When stdout is piped
  (`gensay -v '?' | jq .`), JSON is emitted automatically; a terminal still
  gets the human-readable table.
- **Provider availability in `gensay config show`.** Reports which
  providers are ready based on detected env vars, keychain entries, and
  installed dependencies (test-only providers like `mock` are omitted).

### Fixed

- Unbound `temp_path` crash path in cloud provider playback cleanup.
- Amazon Polly errors are wrapped like other cloud providers, so offline
  fallback can inspect the cause chain.
- Cache keys stringify consistently across providers (existing cache
  entries remain valid).
- Unknown-voice errors suggest the runnable CLI command
  (`gensay -p <provider> -v '?'`) instead of the Python API
  (`list_voices()`).
- Deepgram rejects invalid model strings at construction (its models are
  full voice strings like `flux-haley-en`) instead of failing later or
  silently ignoring them.
- Voice listings through the offline fallback show the real provider name
  (e.g. `OpenAI`) instead of `NetworkFallback`.

### Internal

- Single `ProviderSpec` registry is now the one source of truth for
  provider metadata; CLI choices, daemon hosting, offline-fallback
  eligibility, and `gensay config` keys are all derived from it.
- OpenAI, Deepgram, ElevenLabs, and Polly share the `CloudTTSProvider`
  pipeline (cache → synthesize → play/save → error wrapping); each provider
  implements one `_prepare` hook.
- Provider modules stay lazily imported; CLI startup does not load SDKs.
- New test coverage: registry derivations, cloud base pipeline, plugin API
  stability, and end-to-end plugin discovery through real
  `importlib.metadata` distributions.
