#!/usr/bin/env python3
"""gensay - A multi-provider TTS tool compatible with macOS say command."""

from __future__ import annotations

import argparse
import os
import sys
from importlib.metadata import version as get_pkg_version
from pathlib import Path
from typing import TYPE_CHECKING

# Import lightweight base types only (no heavy provider deps)
from .providers.base import AudioFormat, TTSConfig

if TYPE_CHECKING:
    from .providers.base import TTSProvider

# Provider names for argparse choices (avoid importing heavy modules at top level)
PROVIDER_NAMES = ["chatterbox", "elevenlabs", "macos", "mock", "openai", "polly"]


def get_providers() -> dict:
    """Lazily import and return provider classes."""
    from .providers import (
        AmazonPollyProvider,
        ChatterboxProvider,
        ElevenLabsProvider,
        MacOSSayProvider,
        MockProvider,
        OpenAIProvider,
    )

    return {
        "chatterbox": ChatterboxProvider,
        "elevenlabs": ElevenLabsProvider,
        "macos": MacOSSayProvider,
        "mock": MockProvider,
        "openai": OpenAIProvider,
        "polly": AmazonPollyProvider,
    }


def get_default_provider() -> str:
    """Get the default provider based on the platform or GENSAY_PROVIDER env var."""
    if env_provider := os.environ.get("GENSAY_PROVIDER"):
        if env_provider in PROVIDER_NAMES:
            return env_provider
        else:
            print(
                f"Warning: GENSAY_PROVIDER '{env_provider}' is not valid. "
                f"Valid providers: {', '.join(PROVIDER_NAMES)}",
                file=sys.stderr,
            )

    if sys.platform == "darwin":
        # On macOS, default to the native say command
        return "macos"
    else:
        # On other platforms, default to chatterbox
        return "chatterbox"


def get_version() -> str:
    """Get the package version from installed metadata."""
    try:
        return get_pkg_version("gensay")
    except Exception:
        return "unknown"


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
        "-p",
        "--provider",
        choices=PROVIDER_NAMES,
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

    # Interactive options
    parser.add_argument("-i", "--interactive", help="Interactive mode (not implemented)")
    parser.add_argument("--progress", action="store_true", help="Show progress meter")
    parser.add_argument(
        "--repl",
        action="store_true",
        help="Start interactive REPL mode (provider initialized once, reused for each prompt)",
    )
    parser.add_argument(
        "--listen",
        nargs="?",
        const="/tmp/gensay.pipe",
        metavar="PIPE",
        help="Listen on a named pipe (FIFO) for text input (default: /tmp/gensay.pipe)",
    )

    # Version
    parser.add_argument("--version", action="version", version=f"%(prog)s {get_version()}")

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
        provider_name = provider.__class__.__name__.replace("Provider", "")
        print(f"\nVoices for provider: {provider_name}\n")

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
        from .cache import TTSCache

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
            print(f"  Hits: {stats['hits']}")
            print(f"  Misses: {stats['misses']}")
            print(f"  Directory: {stats['cache_dir']}")

        return True
    return False


def progress_callback(progress: float, message: str) -> None:
    """Default progress callback."""
    if message:
        print(f"\r{message} ({int(progress * 100)}%)", end="", flush=True)
    if progress >= 1.0:
        print()  # New line when complete


def run_repl(provider: TTSProvider, voice: str | None, rate: int | None) -> None:
    """Run interactive REPL mode."""
    print("REPL mode started. Type text to speak, or 'exit'/'quit' to exit.")
    print("Press Ctrl+C or Ctrl+D to exit.\n")

    while True:
        try:
            text = input("gensay> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting REPL.")
            break

        if not text:
            continue
        if text.lower() in ("exit", "quit"):
            print("Exiting REPL.")
            break

        try:
            provider.speak(text, voice=voice, rate=rate)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)


def run_pipe_listener(
    provider: TTSProvider, pipe_path: str, voice: str | None, rate: int | None
) -> None:
    """Listen on a named pipe (FIFO) for text input."""
    import stat

    path = Path(pipe_path)

    # Create FIFO if it doesn't exist
    if not path.exists():
        os.mkfifo(path)
        print(f"Created named pipe: {path}")
    elif not stat.S_ISFIFO(path.stat().st_mode):
        print(f"Error: {path} exists but is not a FIFO", file=sys.stderr)
        sys.exit(1)

    print(f"Listening on {path}")
    print(f"Send text with: echo 'hello' > {path}")
    print("Press Ctrl+C to exit.\n")

    try:
        while True:
            # Open blocks until a writer connects
            with open(path, encoding="utf-8") as fifo:
                for line in fifo:
                    text = line.strip()
                    if not text:
                        continue
                    print(f"Speaking: {text[:50]}{'...' if len(text) > 50 else ''}")
                    try:
                        provider.speak(text, voice=voice, rate=rate)
                    except Exception as e:
                        print(f"Error: {e}", file=sys.stderr)
    except KeyboardInterrupt:
        print("\nExiting pipe listener.")


def main():  # noqa: C901
    """Main entry point."""
    # Parse args first to allow --version to exit early without loading heavy deps
    parser = create_parser()
    args = parser.parse_args()

    # Load environment variables from .env file if present
    from dotenv import load_dotenv

    load_dotenv()

    # Handle cache operations
    if handle_cache_operations(args):
        return

    # Normalize: --voice ? is shorthand for --list-voices (macOS say compatibility)
    if args.voice == "?":
        args.list_voices = True
        args.voice = None

    # Modes that don't require text input
    needs_text = not (args.list_voices or args.repl or args.listen)
    text = get_text_input(args) if needs_text else ""
    if needs_text and not text:
        parser.print_usage()
        sys.exit(1)

    # Configure TTS
    config = TTSConfig(
        voice=args.voice,
        rate=args.rate,
        format=AudioFormat(args.format) if args.format else AudioFormat.M4A,
        cache_enabled=not args.no_cache,
        progress_callback=progress_callback if args.progress else None,
        extra={
            "show_progress": not args.no_progress,
            "chunk_size": args.chunk_size,
        },
    )

    # Warn about slow generation for chatterbox
    if args.provider == "chatterbox":
        print(
            "Note: Chatterbox generation is slow on most consumer hardware, but audio outputs will be cached for re-use.",
            file=sys.stderr,
        )

    # Create provider (lazy import to defer heavy deps)
    try:
        providers = get_providers()
        provider_class = providers[args.provider]
        provider = provider_class(config)
    except NotImplementedError as e:
        print(f"Error: {e}", file=sys.stderr)
        print(f"Provider '{args.provider}' is not yet implemented", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error initializing {args.provider} provider: {e}", file=sys.stderr)
        sys.exit(1)

    # Handle voice listing
    if args.list_voices:
        list_voices(provider)
        return

    # Handle REPL mode
    if args.repl:
        run_repl(provider, args.voice, args.rate)
        return

    # Handle pipe listener mode
    if args.listen:
        run_pipe_listener(provider, args.listen, args.voice, args.rate)
        return

    try:
        # Handle cache-ahead for chatterbox
        if args.cache_ahead and isinstance(provider, providers["chatterbox"]):
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
