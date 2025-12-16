# Development commands for gensay
# https://just.systems/man/en/

# Use bash for all recipes
set shell := ["bash", "-uc"]

# Portaudio paths for pyaudio compilation (supports Nix and Homebrew)
portaudio_path := `nix-build '<nixpkgs>' -A portaudio --no-out-link 2>/dev/null || brew --prefix portaudio 2>/dev/null || echo ""`

export C_INCLUDE_PATH := if portaudio_path != "" { portaudio_path + "/include" } else { "" }
export LIBRARY_PATH := if portaudio_path != "" { portaudio_path + "/lib" } else { "" }

# Default command - show available commands
default:
    @just --list

# Setup development environment
setup:
    uv venv
    uv pip install -e ".[dev]"
    @echo "✓ Development environment ready"

# Install the package in development mode
install:
    uv pip install -e .

# Run all tests
test:
    uv run pytest -v

# Run tests with coverage
test-cov:
    uv run pytest --cov=gensay --cov-report=term-missing --cov-report=html

# Run specific test file or function
test-specific TEST:
    uv run pytest -v {{TEST}}

# Run linter
lint:
    uvx ruff check src tests

# Run linter with auto-fix
lint-fix:
    uvx ruff check --fix src tests

# Format code
format:
    uvx ruff format src tests

# Type check with ty
typecheck:
    uvx ty check ./src

# Run all quality checks (lint, format check, typecheck)
check: lint typecheck
    uvx ruff format --check src tests

# Clean build artifacts and cache
clean:
    rm -rf build dist *.egg-info
    rm -rf .pytest_cache .coverage htmlcov
    rm -rf .ruff_cache .ty_cache
    find . -type d -name "__pycache__" -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete

# Build package
build: clean
    uv build

publish:
    uv publish --username __token__

# Run the CLI with mock provider
run-mock *ARGS:
    gensay --provider mock {{ARGS}}

# Run the CLI with macOS say
run-macos *ARGS:
    gensay --provider macos {{ARGS}}

# List available voices for a provider
list-voices PROVIDER='macos':
    gensay --provider {{PROVIDER}} --list-voices

# Run with ElevenLabs provider (requires ELEVENLABS_API_KEY env var)
run-elevenlabs *ARGS:
    gensay --provider elevenlabs {{ARGS}}

# Test ElevenLabs voices
test-elevenlabs:
    @if [ -z "$ELEVENLABS_API_KEY" ]; then \
        echo "Error: ELEVENLABS_API_KEY environment variable not set"; \
        exit 1; \
    fi
    gensay --provider elevenlabs --list-voices

# Run Chatterbox unit tests (mocked)
test-chatterbox-unit:
    uv run pytest tests/test_chatterbox_provider.py -v -k "Mocked"

# Live integration test for Chatterbox (requires chatterbox-tts installed)
test-chatterbox:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Chatterbox Integration Test ==="
    echo ""
    echo "1. Listing voices..."
    gensay --provider chatterbox --list-voices
    echo ""
    echo "2. Generating speech (short text)..."
    gensay --provider chatterbox "Hello from Chatterbox TTS."
    echo ""
    echo "3. Saving to WAV file..."
    gensay --provider chatterbox -o /tmp/chatterbox-test.wav "This is a file output test."
    ls -la /tmp/chatterbox-test.wav
    echo ""
    echo "4. Saving to MP3 file..."
    gensay --provider chatterbox -o /tmp/chatterbox-test.mp3 "Testing MP3 format export."
    ls -la /tmp/chatterbox-test.mp3
    echo ""
    echo "5. Testing longer text with chunking..."
    gensay --provider chatterbox "This is a longer piece of text that will test the chunking functionality. The text chunker should split this into appropriate segments for the TTS model to process efficiently."
    echo ""
    echo "=== All Chatterbox tests passed ==="

# Run Chatterbox with real model (requires chatterbox-tts installed)
run-chatterbox *ARGS:
    gensay --provider chatterbox {{ARGS}}

# Show cache statistics
cache-stats:
    gensay --cache-stats

# Clear the cache
cache-clear:
    gensay --clear-cache

# Run example script
demo:
    .venv/bin/python examples/demo.py
    .venv/bin/python examples/elevenlabs_demo.py
    .venv/bin/python examples/text_chunking_demo.py

# Run pre-commit checks (lint, format, test)
pre-commit: format lint test
    @echo "✓ All pre-commit checks passed"


quick-test:
    uvx pytest tests/test_providers.py::test_mock_provider_speak -v

# Generate API documentation (requires pdoc)
docs:
    .venv/bin/pdoc -o docs/api src/gensay

# Serve API documentation locally
docs-serve:
    .venv/bin/pdoc -p 8080 src/gensay
