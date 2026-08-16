# gensay usage

```text
usage: gensay [-v voice] [-r rate] [-o outfile] [-f file | message]

Text-to-speech synthesis with multiple providers

positional arguments:
  message               Text message to speak

options:
  -h, --help            show this help message and exit
  -f FILE, --input-file FILE
                        Read text from file (use "-" for stdin)
  -v VOICE, --voice VOICE
                        Select voice by name (use "?" to list voices)
  -r RATE, --rate RATE  Speech rate in words per minute
  -o OUTPUT, --output-file OUTPUT
                        Save audio to file instead of playing
  --format {aiff,wav,m4a,mp3,caf,flac,aac,ogg}
                        Audio format for output file
  --provider {chatterbox,deepgram,elevenlabs,macos,mock,openai,polly}
                        TTS provider to use (default: macos)
  --list-voices         List all available voices for the selected provider
  --no-cache            Disable caching
  --clear-cache         Clear cache and exit
  --cache-stats         Show cache statistics and exit
  --cache-ahead         Pre-cache audio chunks in background (chatterbox only)
  --no-progress         Disable progress bars
  --chunk-size CHUNK_SIZE
                        Text chunk size for processing (default: 500)
  -i, --interactive, --repl
                        Interactive REPL mode (provider initialized once)
  --via-daemon          Require warm daemon
  --no-daemon           Force cold in-process path
  --auto-daemon         Auto-start daemon if missing (warm-eligible)
  --progress            Show progress meter
```

## Daemon

```text
gensay daemon start [-p PROVIDER]   Start background warm daemon
gensay daemon run [-p PROVIDER]     Foreground daemon
gensay daemon status [--json]       Show status
gensay daemon stop                  Stop daemon
gensay daemon restart               Restart daemon
```

## Config (per-user defaults, XDG/platformdirs)

```text
gensay config path                  Print config.toml path
gensay config show [--json]         Show effective defaults
gensay config init [--force]        Write example config.toml
gensay config keys                  List known keys
gensay config get KEY [--effective] [--default VAL]
gensay config set KEY VALUE...
gensay config unset KEY
```

`<provider>.api_key` keys are stored in the OS keychain, not the TOML file.
Omit the value to get a hidden password prompt (keeps secrets out of shell history).

## Cloud provider credentials

Env vars take precedence; see README for full setup.

```bash
# ElevenLabs
export ELEVENLABS_API_KEY   # or once: gensay config set elevenlabs.api_key → OS keychain

# Deepgram
export DEEPGRAM_API_KEY     # or once: gensay config set deepgram.api_key → OS keychain

# OpenAI
export OPENAI_API_KEY       # or once: gensay config set openai.api_key → OS keychain

# Amazon Polly
aws login --region us-west-2            # desktop: opens browser to authorize
aws login --region us-west-2 --remote   # headless: prints a URL to visit
# Updates your default AWS profile with IAM user credentials.
# Tip: sign in to the AWS console in your browser FIRST so the
# authorization above completes without a fresh console login.
# NOTE: boto3 reads AWS_DEFAULT_REGION (NOT AWS_REGION); also export:
export AWS_DEFAULT_REGION=us-west-2
```

## Deepgram notes

- Default model: `flux-haley-en` (Flux TTS, `/v2/speak` batch REST)
- `-v` accepts a short voice name (Flux > Aura-2 > Aura precedence) or a full
  model string: `-v kit` → `flux-kit-en`, `-v aura-2-thalia-en` → `/v1/speak`
- Override the Flux default: `gensay config set deepgram.model <model string>`
- Rate (`-r` WPM): Flux snaps to `{0.85 ... 1.15}`; Aura takes 0.5–2.0 continuously

## Examples

```bash
gensay "Hello, world!"
gensay -v Samantha "Hello from Samantha"
gensay -o greeting.m4a "Welcome"
gensay -f document.txt
echo "Hello" | gensay -f -
gensay --provider chatterbox --cache-ahead "Long text to pre-cache"
gensay --provider deepgram "Default Flux voice (haley)"
gensay -v '?' # List available voices
gensay --provider macos --list-voices # List voices for specific provider
gensay -p deepgram -v '?' --json # Machine-readable: {provider, voices, models}
```

## Hero examples — every provider

### macOS

Built-in; default provider on macOS — no setup.

```bash
gensay "Hello from the Mac"                       # system default voice
gensay -v Samantha -r 200 "A bit faster"          # pick voice + rate
gensay --provider macos --list-voices
```

### Chatterbox

Local AI model; default on non-macOS platforms.

```bash
# Install
uv tool install 'gensay[chatterbox]' \
  --with git+https://github.com/anthonywu/chatterbox.git@allow-dep-updates

# Speak (start the daemon once per session to keep the model warm)
gensay daemon start -p chatterbox
gensay -p chatterbox "Local AI voice, no cloud"
gensay -p chatterbox -o narration.m4a -f chapter.txt
```

### ElevenLabs

Cloud; the extra requires PortAudio (`brew install portaudio`).

```bash
# Install
uv tool install 'gensay[elevenlabs]'

# API key (either; env var wins at runtime)
export ELEVENLABS_API_KEY='<your-key>'          # env var (or .env file)
gensay config set elevenlabs.api_key            # once → prompts (hidden paste) → OS keychain
gensay config unset elevenlabs.api_key          # remove from keychain

# Speak (--provider and -p are equivalent; -v and --voice are equivalent)
gensay --provider elevenlabs "Default voice"
gensay -p elevenlabs -v Rachel "Hello from Rachel"
gensay -p elevenlabs --voice Adam -r 180 "Voice by name, custom rate"
gensay -p elevenlabs -v '?'                     # list voices (same as --list-voices)
gensay -p elevenlabs -o speech.mp3 "Save high-quality audio"

# Defaults via config store
gensay config set elevenlabs.model eleven_multilingual_v2
gensay config set provider elevenlabs           # make it the default provider
gensay config set voice Rachel                  # make it the default voice
```

### Deepgram

Cloud; Flux TTS default, Aura/Aura-2 also available.

```bash
# Install (extra only adds keyring support for config set; core install already speaks)
uv tool install 'gensay[deepgram]'

# API key (either; env var wins at runtime)
export DEEPGRAM_API_KEY='<your-key>'            # env var (or .env file)
gensay config set deepgram.api_key              # once → prompts (hidden paste) → OS keychain
gensay config unset deepgram.api_key            # remove from keychain

# Speak (--provider and -p are equivalent; -v and --voice are equivalent)
gensay --provider deepgram "Default Flux voice (haley)"
gensay -p deepgram -v kit "Short name → newest family (flux-kit-en)"
gensay -p deepgram -v asteria "Short name → aura-2-asteria-en"
gensay -p deepgram --voice aura-asteria-en "Full model string → legacy Aura"
gensay -p deepgram -v aura-2-thalia-en -r 180 "Aura rate is continuous 0.5-2.0x"
gensay -p deepgram -v '?'                       # list Flux + Aura-2 + Aura catalog
gensay -p deepgram -o speech.mp3 "Save to file"

# Defaults via config store
gensay config set deepgram.model flux-kit-en    # override the flux-haley-en default
gensay config set provider deepgram             # make it the default provider
```

### OpenAI

Cloud.

```bash
# API key (either; env var wins at runtime)
export OPENAI_API_KEY='sk-...'                  # env var (or .env file)
gensay config set openai.api_key                # once → prompts (hidden paste) → OS keychain
gensay config unset openai.api_key              # remove from keychain
# keychain storage needs the keyring package: pip install 'gensay[keychain]'

# Speak (--provider and -p are equivalent; -v and --voice are equivalent)
gensay --provider openai "Default voice"
gensay -p openai -v nova "Hello from nova"
gensay -p openai --voice onyx -r 180 "Deeper voice, custom rate"
gensay -p openai -v '?'                         # alloy ash ballad coral echo fable onyx nova sage shimmer
gensay -p openai -o speech.mp3 "Save to file"

# Defaults via config store
gensay config set openai.model tts-1-hd         # higher quality (default: tts-1)
gensay -p openai -m gpt-4o-mini-tts "One-off model override"   # or --model
gensay config set provider openai               # make it the default provider
```

### Amazon Polly

Cloud; auth via the standard AWS credential chain, not gensay config.

```bash
# Credentials (either)
export AWS_ACCESS_KEY_ID='AKIA...'              # IAM user with AmazonPollyReadOnlyAccess
export AWS_SECRET_ACCESS_KEY='...'
export AWS_DEFAULT_REGION=us-west-2             # boto3 reads AWS_DEFAULT_REGION, not AWS_REGION
# — or sign in with AWS CLI v2 (writes ~/.aws credentials, the AWS "config store"):
aws login --region us-west-2                    # desktop: opens browser
aws login --region us-west-2 --remote           # headless: prints URL to visit

# Speak (--provider and -p are equivalent; -v and --voice are equivalent)
gensay --provider polly "Default voice"
gensay -p polly -v Joanna "Hello from Amazon Polly"
gensay -p polly --voice Matthew -r 180 "Voice by name, custom rate"
gensay -p polly -v '?'                          # 60+ voices, many languages
gensay -p polly -o speech.mp3 "Save to file"

# Defaults via config store
gensay config set polly.engine standard         # standard | neural | long-form | generative (default: neural)
gensay config set polly.aws_profile my-profile  # named AWS profile (SSO, assume-role, ...)
gensay config set polly.aws_region us-west-2    # region override
gensay config set provider polly                # make it the default provider
```

### Mock

Testing; no audio, no setup.

```bash
gensay --provider mock "Dry-run the CLI without real TTS"
gensay --provider mock --list-voices
```

### Works with every provider

```bash
gensay --provider <name> --list-voices            # discover voices
gensay --provider <name> -v '?'                   # same, shorthand
gensay --provider <name> -o out.m4a "text"        # save instead of play
echo "text" | gensay --provider <name> -f -       # read from stdin
```

## Provider plugins (third-party)

Packages can add providers via the `gensay.providers` entry-point group.
The entry point must resolve to a `ProviderSpec`; keep that module cheap to
import — the provider class itself is only imported when selected.

```toml
# pyproject.toml of your plugin package
[project.entry-points."gensay.providers"]
acme = "acme_tts:GENSAY_PROVIDER_SPEC"
```

```python
# acme_tts/__init__.py — import-cheap module
from gensay.plugin import ProviderSpec

GENSAY_PROVIDER_SPEC = ProviderSpec(
    name="acme",
    class_name="AcmeProvider",          # subclass of TTSProvider
    module="acme_tts.provider",         # imported lazily on first use
    kind="cloud",
    env_api_key="ACME_API_KEY",
    config_keys=(("api_key", str), ("model", str)),
)
```

Everything a plugin needs — `ProviderSpec`, `TTSProvider`,
`CloudTTSProvider`, `PreparedSynthesis`, `TTSConfig`, `AudioFormat` — is
importable from the stable `gensay.plugin` module; don't depend on internal
`gensay.providers.*` paths, which may move between releases.

Cloud providers should subclass `CloudTTSProvider` and implement one hook
(`_prepare`) plus `list_voices` / `get_supported_formats`; caching,
playback, progress, and error wrapping come from the base class. Installed
plugins appear in `--provider` choices and `gensay config keys`
automatically; names that collide with builtins are skipped with a warning.

A complete installable example lives in
[`examples/gensay-plugin-example`](examples/gensay-plugin-example/) — an
offline provider that beeps text as sine-wave tones:

```bash
uv pip install ./examples/gensay-plugin-example
gensay -p tone "hello plugins"
```
