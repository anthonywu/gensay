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
  --provider {chatterbox,macos,mock,openai,elevenlabs,polly}
                        TTS provider to use (default: macos)
  --list-voices         List all available voices for the selected provider
  --no-cache            Disable caching
  --clear-cache         Clear cache and exit
  --cache-stats         Show cache statistics and exit
  --cache-ahead         Pre-cache audio chunks in background (chatterbox only)
  --no-progress         Disable progress bars
  --chunk-size CHUNK_SIZE
                        Text chunk size for processing (default: 500)
  -i INTERACTIVE, --interactive INTERACTIVE
                        Interactive mode (not implemented)
  --progress            Show progress meter

Examples:
  gensay "Hello, world!"
  gensay -v Samantha "Hello from Samantha"
  gensay -o greeting.m4a "Welcome"
  gensay -f document.txt
  echo "Hello" | gensay -f -
  gensay --provider chatterbox --cache-ahead "Long text to pre-cache"
  gensay -v '?' # List available voices
  gensay --provider macos --list-voices # List voices for specific provider
