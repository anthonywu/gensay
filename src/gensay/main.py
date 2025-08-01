#!/usr/bin/env python3
"""gensay - A multi-provider TTS tool compatible with macOS say command."""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from .cache import TTSCache
from .providers import (
    AmazonPollyProvider,
    AudioFormat,
    ChatterboxProvider,
    ElevenLabsProvider,
    MacOSSayProvider,
    MockProvider,
    OpenAIProvider,
    TTSConfig,
    TTSProvider,
)

PROVIDERS = {
    "chatterbox": ChatterboxProvider,
    "macos": MacOSSayProvider,
    "mock": MockProvider,
    "openai": OpenAIProvider,
    "elevenlabs": ElevenLabsProvider,
    "polly": AmazonPollyProvider,
}


def get_default_provider() -> str:
    """Get the default provider based on the platform."""
    if sys.platform == "darwin":
        # On macOS, default to the native say command
        return "macos"
    else:
        # On other platforms, default to chatterbox
        return "chatterbox"


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser matching macOS say command."""
    parser = argparse.ArgumentParser(
        prog="gensay",
        description="Text-to-speech synthesis with multiple providers",
        usage="gensay [-v voice] [-r rate] [-o outfile] [-f file | message]",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  gensay "Hello, world!"
  gensay -v Samantha "Hello from Samantha"
  gensay -o greeting.m4a "Welcome"
  gensay -f document.txt
  echo "Hello" | gensay -f -
  gensay --provider chatterbox --cache-ahead "Long text to pre-cache"
  gensay -v '?' # List available voices
  gensay --provider macos --list-voices # List voices for specific provider""",
    )

    # Text input options
    parser.add_argument("message", nargs="*", default=[], help="Text message to speak")
    parser.add_argument(
        "-f", "--input-file", dest="file", help='Read text from file (use "-" for stdin)'
    )

    # Voice and rate options
    parser.add_argument("-v", "--voice", help='Select voice by name (use "?" to list voices)')
    parser.add_argument("-r", "--rate", type=int, help="Speech rate in words per minute")

    # Output options
    parser.add_argument(
        "-o", "--output-file", dest="output", help="Save audio to file instead of playing"
    )
    parser.add_argument(
        "--format", choices=[f.value for f in AudioFormat], help="Audio format for output file"
    )

    # Provider options
    default_provider = get_default_provider()
    parser.add_argument(
        "--provider",
        choices=list(PROVIDERS.keys()),
        default=default_provider,
        help=f"TTS provider to use (default: {default_provider})",
    )

    # Voice options
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List all available voices for the selected provider",
    )

    # Advanced options
    parser.add_argument("--no-cache", action="store_true", help="Disable caching")
    parser.add_argument("--clear-cache", action="store_true", help="Clear cache and exit")
    parser.add_argument("--cache-stats", action="store_true", help="Show cache statistics and exit")
    parser.add_argument(
        "--cache-ahead",
        action="store_true",
        help="Pre-cache audio chunks in background (chatterbox only)",
    )
    parser.add_argument("--no-progress", action="store_true", help="Disable progress bars")
    parser.add_argument(
        "--chunk-size", type=int, default=500, help="Text chunk size for processing (default: 500)"
    )

    # Interactive options (for compatibility)
    parser.add_argument("-i", "--interactive", help="Interactive mode (not implemented)")
    parser.add_argument("--progress", action="store_true", help="Show progress meter")

    return parser


def get_text_input(args) -> str:
    """Get text input from command line arguments."""
    # Check for mutual exclusivity
    if args.message and args.file:
        print("Error: Cannot specify both message and -f option", file=sys.stderr)
        sys.exit(1)

    if args.message:
        # Join multiple words from positional arguments
        return " ".join(args.message)
    elif args.file:
        if args.file == "-":
            # Read from stdin
            return sys.stdin.read().strip()
        else:
            # Read from file
            try:
                with open(args.file, encoding="utf-8") as f:
                    return f.read().strip()
            except FileNotFoundError:
                print(f"Error: File '{args.file}' not found", file=sys.stderr)
                sys.exit(1)
            except Exception as e:
                print(f"Error reading file: {e}", file=sys.stderr)
                sys.exit(1)
    else:
        # No input provided
        return ""


def list_voices(provider: TTSProvider) -> None:
    """List available voices."""
    try:
        voices = provider.list_voices()
        if not voices:
            print("No voices available", file=sys.stderr)
            return

        # Format similar to macOS say command
        for voice in voices:
            # Use name if available, otherwise use id
            display_name = voice.get("name", voice["id"])
            lang = voice.get("language", "Unknown")
            desc = voice.get("description", "")

            # Add additional info to description if available
            extra_info = []
            if "use_case" in voice and voice["use_case"]:
                extra_info.append(voice["use_case"])
            if "accent" in voice and voice["accent"]:
                extra_info.append(voice["accent"])
            if "age" in voice and voice["age"]:
                extra_info.append(voice["age"])

            if extra_info:
                desc = f"{desc} - {', '.join(extra_info)}" if desc else ", ".join(extra_info)

            if desc:
                print(f"{display_name:<20} {lang:<10} # {desc}")
            else:
                print(f"{display_name:<20} {lang:<10}")
    except NotImplementedError:
        print(f"Voice listing not implemented for {provider.__class__.__name__}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error listing voices: {e}", file=sys.stderr)
        sys.exit(1)


def handle_cache_operations(args) -> bool:
    """Handle cache-related operations. Returns True if handled."""
    if args.clear_cache or args.cache_stats:
        cache = TTSCache()

        if args.clear_cache:
            cache.clear()
            print("Cache cleared successfully")

        if args.cache_stats:
            stats = cache.get_stats()
            print("Cache Statistics:")
            print(f"  Enabled: {stats['enabled']}")
            print(f"  Items: {stats['items']}")
            print(f"  Size: {stats['size_mb']:.2f} MB / {stats['max_size_mb']} MB")
            print(f"  Directory: {stats['cache_dir']}")

        return True
    return False


def progress_callback(progress: float, message: str) -> None:
    """Default progress callback."""
    if message:
        print(f"\r{message} ({int(progress * 100)}%)", end="", flush=True)
    if progress >= 1.0:
        print()  # New line when complete


def main():  # noqa: C901
    """Main entry point."""
    # Load environment variables from .env file if present
    load_dotenv()

    parser = create_parser()
    args = parser.parse_args()

    # Handle cache operations
    if handle_cache_operations(args):
        return

    # Get text input
    text = get_text_input(args)
    if not text and args.voice != "?" and not args.list_voices:
        parser.print_usage()
        sys.exit(1)

    # Configure TTS
    config = TTSConfig(
        voice=args.voice if args.voice != "?" else None,
        rate=args.rate,
        format=AudioFormat(args.format) if args.format else AudioFormat.M4A,
        cache_enabled=not args.no_cache,
        progress_callback=progress_callback if args.progress else None,
        extra={
            "show_progress": not args.no_progress,
            "chunk_size": args.chunk_size,
        },
    )

    # Create provider
    try:
        provider_class = PROVIDERS[args.provider]
        provider = provider_class(config)
    except NotImplementedError as e:
        print(f"Error: {e}", file=sys.stderr)
        print(f"Provider '{args.provider}' is not yet implemented", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error initializing {args.provider} provider: {e}", file=sys.stderr)
        sys.exit(1)

    # Handle voice listing
    if args.voice == "?" or args.list_voices:
        list_voices(provider)
        return

    try:
        # Handle cache-ahead for chatterbox
        if args.cache_ahead and isinstance(provider, ChatterboxProvider):
            print("Pre-caching audio chunks...")
            provider.cache_ahead(text, args.voice, args.rate)
            print("Cache-ahead started in background")

        # Generate speech
        if args.output:
            # Save to file
            output_path = Path(args.output)
            if args.format:
                format = AudioFormat(args.format)
            else:
                format = AudioFormat.from_extension(output_path)

            result = provider.save_to_file(
                text, output_path, voice=args.voice, rate=args.rate, format=format
            )
            print(f"Audio saved to {result}")
        else:
            # Speak directly
            provider.speak(text, voice=args.voice, rate=args.rate)

    except NotImplementedError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
