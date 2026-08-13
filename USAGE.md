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

Daemon:
  gensay daemon start [-p PROVIDER]   Start background warm daemon
  gensay daemon run [-p PROVIDER]     Foreground daemon
  gensay daemon status [--json]       Show status
  gensay daemon stop                  Stop daemon
  gensay daemon restart               Restart daemon

Config (per-user defaults, XDG/platformdirs):
  gensay config path                  Print config.toml path
  gensay config show [--json]         Show effective defaults
  gensay config init [--force]        Write example config.toml
  gensay config keys                  List known keys
  gensay config get KEY [--effective] [--default VAL]
  gensay config set KEY VALUE...
  gensay config unset KEY
  # <provider>.api_key keys are stored in the OS keychain, not the TOML file

Cloud provider credentials (env vars take precedence; see README for full setup):
  ElevenLabs:   export ELEVENLABS_API_KEY   (or once: gensay config set elevenlabs.api_key → OS keychain)
  Deepgram:     export DEEPGRAM_API_KEY     (or once: gensay config set deepgram.api_key → OS keychain)
  OpenAI:       export OPENAI_API_KEY
  Amazon Polly: aws login --region us-west-2            # desktop: opens browser to authorize
                aws login --region us-west-2 --remote   # headless: prints a URL to visit
                # Updates your default AWS profile with IAM user credentials.
                # Tip: sign in to the AWS console in your browser FIRST so the
                # authorization above completes without a fresh console login.
                # NOTE: boto3 reads AWS_DEFAULT_REGION (NOT AWS_REGION); also export:
                export AWS_DEFAULT_REGION=us-west-2

Deepgram notes:
  Default model: flux-haley-en (Flux TTS, /v2/speak batch REST)
  -v accepts a short voice name (Flux > Aura-2 > Aura precedence) or a full
  model string: -v kit  →  flux-kit-en,  -v aura-2-thalia-en  →  /v1/speak
  Override the Flux default:  gensay config set deepgram.model <model string>
  Rate (-r WPM): Flux snaps to {0.85 ... 1.15}; Aura takes 0.5-2.0 continuously

Examples:
  gensay "Hello, world!"
  gensay -v Samantha "Hello from Samantha"
  gensay -o greeting.m4a "Welcome"
  gensay -f document.txt
  echo "Hello" | gensay -f -
  gensay --provider chatterbox --cache-ahead "Long text to pre-cache"
  gensay --provider deepgram "Default Flux voice (haley)"
  gensay -v '?' # List available voices
  gensay --provider macos --list-voices # List voices for specific provider
