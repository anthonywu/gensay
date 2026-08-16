# gensay-tone — example provider plugin

A complete, installable gensay provider plugin. It "speaks" text as
sine-wave tones (one beep per character) using only the Python stdlib, so
it works offline with no API keys — it exists to show the plugin shape,
not to be useful TTS.

## Anatomy

```text
pyproject.toml               entry point: [project.entry-points."gensay.providers"]
src/gensay_tone/__init__.py  import-cheap: just the ProviderSpec
src/gensay_tone/provider.py  ToneProvider, imported lazily on first use
```

The rules a plugin must follow:

1. Register an entry point in the `gensay.providers` group that resolves to
   a `ProviderSpec` instance.
2. Keep the entry-point module cheap to import (no SDKs, no models); gensay
   imports every installed plugin's spec at startup.
3. Import everything from `gensay.plugin` (the stable public API), not from
   internal `gensay.providers.*` paths.
4. Implement the provider class named by the spec — subclass
   `CloudTTSProvider` for network backends (implement `_prepare`,
   `list_voices`, `get_supported_formats`) or `TTSProvider` for anything
   else, as done here.

## Try it

```bash
uv pip install ./examples/gensay-plugin-example

gensay --help                      # "tone" now appears in --provider choices
gensay -p tone "hello plugins"     # beeps
gensay -p tone -v '?'              # low / mid / high
gensay -p tone -v high -r 300 -o beeps.wav "faster and higher"
```
