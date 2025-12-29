# Provider Validation Tests

## Overview

The `test_provider_validation.py` module provides integration tests for all TTS providers to validate they work correctly without cache dependencies.

## Test Design

Each test:
1. Creates a provider instance with `cache_enabled=False` (fresh generation)
2. Selects 2 voices from the provider
3. Generates audio for each voice
4. Saves to `tests/artifacts/{provider}/{voice}.{ext}`
5. Verifies file was created and has reasonable size

## Test Coverage

| Provider | Voices Tested | File Format | Test Status |
|-----------|---------------|---------------|---------------|
| macOS      | 2 English voices (Albert, Aman) | .m4a | ✓ Passed |
| Mock       | 2 mock voices | .m4a | ✓ Passed |
| Chatterbox | 2 voices (default, custom) | .m4a | ✓ Passed |
| OpenAI     | 2 voices (alloy, ash) | .mp3 | ✓ Passed |
| ElevenLabs | 2 voices (Sarah, Roger) | .mp3 | ✓ Passed |
| Amazon Polly| 2 English voices | .mp3 | ○ Skipped (no credentials) |

## Running the Tests

```bash
# Run all provider validation tests
pytest tests/test_provider_validation.py -v

# Run specific provider
pytest tests/test_provider_validation.py::test_macos_provider -v

# Run with detailed output
pytest tests/test_provider_validation.py -v -s
```

## Artifacts

Generated files are saved to `tests/artifacts/{provider}/`:

```
tests/artifacts/
├── .gitkeep
├── macos/
│   ├── Albert.m4a      (52KB)
│   └── Aman.m4a        (45KB)
├── mock/
│   ├── mock-voice-1.m4a (160B)
│   └── mock-voice-2.m4a (160B)
├── chatterbox/
│   ├── default.m4a       (41KB)
│   └── custom.m4a        (42KB)
├── openai/
│   ├── alloy.mp3        (61KB)
│   └── ash.mp3          (57KB)
└── elevenlabs/
    ├── Sarah_-_Mature,_Reassuring,_Confident.mp3  (46KB)
    └── Roger_-_Laid-Back,_Casual,_Resonant.mp3   (40KB)
```

## Cache Behavior

Tests explicitly disable caching to validate fresh generation:
- `config = TTSConfig(cache_enabled=False)`
- This ensures providers work correctly without existing cached data
- Useful for validating provider changes or API integrations

## Skipping Tests

Tests are skipped when:
- Platform mismatch (macOS provider on non-macOS)
- Missing dependencies (ImportError)
- Missing API keys (ValueError for cloud providers)
- Missing AWS credentials (RuntimeError for Polly)

## Notes

- Amazon Polly test is skipped by default (requires AWS credentials)
- Mock provider generates small dummy files (160B)
- Real providers generate files ranging from 40KB-60KB for the test text
- All artifacts are gitignored (see `.gitignore`)
