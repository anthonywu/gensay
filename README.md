# gensay

[![PyPI - Version](https://img.shields.io/pypi/v/gensay.svg)](https://pypi.org/project/gensay)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/gensay.svg)](https://pypi.org/project/gensay)

A multi-provider text-to-speech (TTS) tool that implements the Apple macOS `/usr/bin/say` command interface while supporting multiple TTS backends including Chatterbox (local AI), OpenAI, ElevenLabs, and Amazon Polly.

## Features

- **macOS `say` Compatible**: Drop-in replacement for the macOS `say` command with identical CLI interface
- **Multiple TTS Providers**: Extensible provider system with support for:
  - macOS native `say` command (default on macOS)
  - Chatterbox (local AI TTS, default on other platforms)
  - ElevenLabs (cloud API)
  - OpenAI TTS (cloud API)
  - Amazon Polly (cloud API)
  - Mock provider for testing
- **Smart Text Chunking**: Intelligently splits long text for optimal TTS processing
- **Audio Caching**: Automatic caching with LRU eviction to speed up repeated synthesis
- **Progress Tracking**: Built-in progress bars with tqdm and customizable callbacks
- **Multiple Audio Formats**: Support for AIFF, WAV, M4A, MP3, CAF, FLAC, AAC, OGG
- **Background Pre-caching**: Queue and cache audio chunks in the background (Chatterbox only)

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Command Line Usage](#command-line-usage)
- [Python API](#python-api)
- [Provider Configurations](#provider-configurations)
- [Advanced Features](#advanced-features)
- [Development](#development)
- [License](#license)

## Installation

It's 2025, use [uv](https://github.com/astral-sh/uv)

`gensay` is intended to be used as a CLI tool that is a drop-in replacement to the macOS `say` CLI.

### System Dependencies (ElevenLabs provider only)

**PortAudio is required** if you plan to use the ElevenLabs provider. The `pyaudio` dependency needs the PortAudio C library to compile successfully.

Other providers (macOS, OpenAI, Amazon Polly, Chatterbox) do not require PortAudio.

**Homebrew (macOS):**

```bash
brew install portaudio
```

**Nix:**

```bash
nix-env -iA nixpkgs.portaudio
```

### Installation

```console
# Install as a tool
uv tool install gensay

# Or add to your project
uv add gensay

# From source (with automatic PortAudio path configuration)
git clone https://github.com/anthonywu/gensay
cd gensay
just setup
```

### Optional Provider Dependencies

Some providers require additional dependencies:

```bash
# Chatterbox provider (local AI TTS, ~2GB PyTorch dependencies)
uv tool install 'gensay[chatterbox]' \
  --with git+https://github.com/anthonywu/chatterbox.git@allow-dep-updates
# or with pip
pip install 'gensay[chatterbox]'
pip install git+https://github.com/anthonywu/chatterbox.git@allow-dep-updates

# ElevenLabs provider (requires PortAudio, see above)
pip install 'gensay[elevenlabs]'
```

**Installation Help:**

- [PyAudio documentation](https://pypi.org/project/PyAudio/) - For PortAudio/PyAudio installation issues
- [ElevenLabs Python library docs](https://elevenlabs.io/docs/agents-platform/libraries/python) - Official ElevenLabs Python documentation

For source installation, `just setup` automatically configures the PortAudio include/library paths for both Nix and Homebrew installations.

Or manually set the paths before installing:

```bash
export C_INCLUDE_PATH="$(nix-build '<nixpkgs>' -A portaudio --no-out-link)/include:$C_INCLUDE_PATH"
export LIBRARY_PATH="$(nix-build '<nixpkgs>' -A portaudio --no-out-link)/lib:$LIBRARY_PATH"
uv pip install -e .
```

## Quick Start

```bash
# Basic usage - speaks the text
gensay "Hello, world!"

# Use specific voice
gensay -v Samantha "Hello from Samantha"

# Save to audio file
gensay -o greeting.m4a "Welcome to gensay"

# List available voices (two ways)
gensay -v '?'
gensay --list-voices
```

## Command Line Usage

### Basic Options

```bash
# Speak text
gensay "Hello, world!"

# Read from file
gensay -f document.txt

# Read from stdin
echo "Hello from pipe" | gensay -f -

# Specify voice
gensay -v Alex "Hello from Alex"

# Adjust speech rate (words per minute)
gensay -r 200 "Speaking faster"

# Save to file
gensay -o output.m4a "Save this speech"

# Specify audio format
gensay -o output.wav --format wav "Different format"
```

### Provider Selection

```bash
# Use macOS native say command
gensay --provider macos "Using system TTS"

# List voices for specific provider
gensay --provider macos --list-voices
gensay --provider mock --list-voices

# Use mock provider for testing
gensay --provider mock "Testing without real TTS"

# Use Chatterbox explicitly
gensay --provider chatterbox "Local AI voice"

# Default provider depends on platform
gensay "Hello"  # Uses 'macos' on macOS, 'chatterbox' on other platforms
```

### Advanced Options

```bash
# Show progress bar
gensay --progress "Long text with progress tracking"

# Pre-cache audio chunks in background
gensay --provider chatterbox --cache-ahead "Pre-process this text"

# Adjust chunk size
gensay --chunk-size 1000 "Process in larger chunks"

# Cache management
gensay --cache-stats     # Show cache statistics
gensay --clear-cache     # Clear all cached audio
gensay --no-cache "Text" # Disable cache for this run
```

## Python API

### Basic Usage

```python
from gensay import ChatterboxProvider, TTSConfig, AudioFormat

# Create provider
provider = ChatterboxProvider()

# Speak text
provider.speak("Hello from Python")

# Save to file
provider.save_to_file("Save this", "output.m4a")

# List voices
voices = provider.list_voices()
for voice in voices:
    print(f"{voice['id']}: {voice['name']}")
```

### Advanced Configuration

```python
from gensay import ChatterboxProvider, TTSConfig, AudioFormat

# Configure TTS
config = TTSConfig(
    voice="default",
    rate=150,
    format=AudioFormat.M4A,
    cache_enabled=True,
    extra={
        'show_progress': True,
        'chunk_size': 500
    }
)

# Create provider with config
provider = ChatterboxProvider(config)

# Add progress callback
def on_progress(progress: float, message: str):
    print(f"Progress: {progress:.0%} - {message}")

config.progress_callback = on_progress

# Use the configured provider
provider.speak("Text with all options configured")
```

### Text Chunking

```python
from gensay import chunk_text_for_tts, TextChunker

# Simple chunking
chunks = chunk_text_for_tts(long_text, max_chunk_size=500)

# Advanced chunking with custom strategy
chunker = TextChunker(
    max_chunk_size=1000,
    strategy="paragraph",  # or "sentence", "word", "character"
    overlap_size=50
)
chunks = chunker.chunk_text(document)
```

## Provider Configurations

### ElevenLabs

1. Install the optional dependency (requires PortAudio):
   ```bash
   pip install 'gensay[elevenlabs]'
   ```
2. Get an API key from [ElevenLabs](https://elevenlabs.io)
3. Set the environment variable:
   ```bash
   export ELEVENLABS_API_KEY="your-api-key"
   ```

```bash
# List ElevenLabs voices
gensay --provider elevenlabs --list-voices

# Use a specific ElevenLabs voice
gensay --provider elevenlabs -v Rachel "Hello from ElevenLabs"

# Save to file with high quality
gensay --provider elevenlabs -o speech.mp3 "High quality AI speech"
```

### OpenAI TTS

1. Get an API key from [OpenAI Platform](https://platform.openai.com/api-keys)
2. Set the environment variable:
   ```bash
   export OPENAI_API_KEY="sk-..."
   ```

```bash
# List OpenAI voices
gensay --provider openai --list-voices

# Use a specific voice (alloy, ash, ballad, coral, echo, fable, onyx, nova, sage, shimmer)
gensay --provider openai -v nova "Hello from OpenAI"

# Save to file
gensay --provider openai -o speech.mp3 "OpenAI TTS output"
```

OpenAI offers two models via `config.extra['model']`:

- `tts-1` (default): Faster, lower latency
- `tts-1-hd`: Higher quality audio

### Amazon Polly

**Option A - Environment variables:**

1. Sign in to [AWS Console](https://console.aws.amazon.com/)
2. Go to **IAM** → **Users** → **Create user**
3. Attach the `AmazonPollyReadOnlyAccess` policy
4. Create access keys under **Security credentials** → **Access keys**
5. Configure credentials (choose one method):

```bash
export AWS_ACCESS_KEY_ID="AKIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_DEFAULT_REGION="us-west-2"
```

**Option B - AWS CLI v2:**

This easy lets you [sign in through the AWS Command Line Interface](https://docs.aws.amazon.com/signin/latest/userguide/command-line-sign-in.html)

```bash
export AWS_DEFAULT_REGION=us-west-2
# on your desktop with a browser
aws login --region
# in an env without a browser
aws login --region --remote
```

#### Polly Usage

```bash
# List Polly voices (60+ voices in many languages)
gensay --provider polly --list-voices

# Use a specific voice
gensay --provider polly -v Joanna "Hello from Amazon Polly"

# Save to file
gensay --provider polly -o speech.mp3 "Polly TTS output"
```

Polly supports multiple engines via `config.extra['engine']`:

- `neural` (default): Higher quality, natural-sounding
- `standard`: Lower cost, available for all voices

## Advanced Features

### Caching System

The caching system automatically stores generated audio to speed up repeated synthesis:

```python
from gensay import TTSCache

# Create cache instance
cache = TTSCache(
    enabled=True,
    max_size_mb=10000,
    max_items=1000
)

# Get cache statistics
stats = cache.get_stats()
print(f"Cache size: {stats['size_mb']:.2f} MB")
print(f"Cached items: {stats['items']}")

# Clear cache
cache.clear()
```

**Cache Location**

Cache files are stored in platform-specific user cache directories:

- **macOS**: `~/Library/Caches/gensay`
- **Linux**: `~/.cache/gensay`
- **Windows**: `%LOCALAPPDATA%\gensay\gensay\Cache`

**Managing Cache**

```bash
# Show cache statistics
gensay --cache-stats

# Clear all cached audio
gensay --clear-cache

# Disable caching for a specific command
gensay --no-cache "Text to synthesize without caching"
```

**Manual Deletion**

To manually delete the cache, remove the cache directory:

```bash
# macOS/Linux
rm -rf ~/Library/Caches/gensay  # macOS
rm -rf ~/.cache/gensay          # Linux

# Windows (PowerShell)
Remove-Item -Recurse -Force $env:LOCALAPPDATA\gensay\gensay\Cache
```

### Creating Custom Providers

```python
from gensay.providers import TTSProvider, TTSConfig, AudioFormat
from typing import Optional, Union, Any
from pathlib import Path

class MyCustomProvider(TTSProvider):
    def speak(self, text: str, voice: Optional[str] = None,
              rate: Optional[int] = None) -> None:
        # Your implementation
        self.update_progress(0.5, "Halfway done")
        # ... generate and play audio ...
        self.update_progress(1.0, "Complete")

    def save_to_file(self, text: str, output_path: Union[str, Path],
                     voice: Optional[str] = None, rate: Optional[int] = None,
                     format: Optional[AudioFormat] = None) -> Path:
        # Your implementation
        return Path(output_path)

    def list_voices(self) -> list[dict[str, Any]]:
        return [
            {'id': 'voice1', 'name': 'Voice One', 'language': 'en-US'}
        ]

    def get_supported_formats(self) -> list[AudioFormat]:
        return [AudioFormat.WAV, AudioFormat.MP3]
```

### Async Support

All providers support async operations:

```python
import asyncio
from gensay import ChatterboxProvider

async def main():
    provider = ChatterboxProvider()

    # Async speak
    await provider.speak_async("Async speech")

    # Async save
    await provider.save_to_file_async("Async save", "output.m4a")

asyncio.run(main())
```

## Development

This project uses [just](https://just.systems) for common development tasks. First, install just:

```bash
# macOS (using Nix which you already have)
nix-env -iA nixpkgs.just

# Or using Homebrew
brew install just

# Or using cargo
cargo install just
```

### Quick Start

```bash
# Setup development environment
just setup

# Run tests
just test

# Run all quality checks
just check

# See all available commands
just
```

### Common Development Commands

#### Testing

```bash
# Run all tests
just test

# Run tests with coverage
just test-cov

# Run specific test
just test-specific tests/test_providers.py::test_mock_provider_speak

# Quick test (mock provider only)
just quick-test
```

#### Code Quality

```bash
# Run linter
just lint

# Auto-fix linting issues
just lint-fix

# Format code
just format

# Type checking
just typecheck

# Run all checks (lint, format, typecheck)
just check

# Pre-commit checks (format, lint, test)
just pre-commit
```

#### Running the CLI

```bash
# Run with mock provider
just run-mock "Hello, world!"
just run-mock -v '?'

# Run with macOS provider
just run-macos "Hello from macOS"

# Cache management
just cache-stats
just cache-clear
```

#### Development Utilities

```bash
# Run example script
just demo

# Clean build artifacts
just clean

# Build package
just build
```

### Manual Setup (without just)

If you prefer not to use just, here are the equivalent commands:

```bash
# Setup
uv venv
uv pip install -e ".[dev]"

# Testing
uv run pytest -v
uv run pytest --cov=gensay --cov-report=term-missing

# Linting and formatting
uv run ruff check src tests
uv run ruff format src tests

# Type checking
uvx ty check src
```

### Project Structure

```
gensay/
├── src/gensay/
│   ├── __init__.py
│   ├── main.py              # CLI entry point
│   ├── providers/           # TTS provider implementations
│   │   ├── base.py         # Abstract base provider
│   │   ├── chatterbox.py   # Chatterbox provider
│   │   ├── macos_say.py    # macOS say wrapper
│   │   └── ...            # Other providers
│   ├── cache.py            # Caching system
│   └── text_chunker.py     # Text chunking logic
├── tests/                  # Test suite
├── examples/               # Example scripts
├── justfile                # Development commands
└── README.md
```

### Code Style Guide

- Python 3.11+ with type hints
- Follow PEP8 and Google Python Style Guide
- Use `ruff` for linting and formatting
- Keep docstrings concise but informative
- Prefer `pathlib.Path` over `os.path`
- Use `pytest` for testing

## License

`gensay` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
