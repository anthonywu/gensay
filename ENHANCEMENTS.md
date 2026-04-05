# Recommended Enhancements for gensay

After a thorough analysis of the codebase, here are prioritized enhancement
recommendations organized by category.

---

## 1. CI/CD and Developer Experience

### 1a. Add a CI test workflow (High Priority)

Currently the only GitHub Actions workflow is `security.yml` (pip-audit). There
is no automated test run on PRs or pushes. Adding one would catch regressions
before merge.

**Suggested file:** `.github/workflows/test.yml`

```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv python install ${{ matrix.python-version }}
      - run: uv sync --python ${{ matrix.python-version }}
      - run: uv run pytest --cov=gensay --cov-report=xml -v
      - uses: codecov/codecov-action@v4  # optional
```

### 1b. Add lint/typecheck to CI (Medium Priority)

The `just check` recipe runs ruff + ty locally, but neither runs in CI. A
simple job that runs `uvx ruff check src tests && uvx ruff format --check src
tests` would enforce style on PRs.

### 1c. Automated release workflow (Low Priority)

A workflow triggered on version tags (`v*`) could build and publish to PyPI
automatically, replacing the manual `just publish` step.

---

## 2. Dependency Hygiene

### 2a. Make cloud SDKs optional (High Priority)

`boto3`, `botocore[crt]`, `openai`, and `hf-transfer` are listed as **core**
dependencies but are only needed by specific providers. A user who only wants
the macOS `say` wrapper or ElevenLabs is forced to download the entire AWS SDK
and OpenAI client.

**Suggested change:**

```toml
[project]
dependencies = [
    "diskcache>=5.6.3,<6.0",
    "distro>=1.9.0,<2.0",
    "platformdirs>=4.3,<5.0",
    "psutil>=7.0,<8.0",
    "python-dotenv>=1.1.1,<2.0",
    "tqdm>=4.67,<5.0",
]

[project.optional-dependencies]
openai = ["openai>=1.98.0,<2.0"]
polly = ["boto3>=1.40.0,<2.0", "botocore[crt]>=1.40.0,<2.0"]
chatterbox = [..., "hf-transfer>=0.1.9,<1.0"]
```

The providers already use lazy imports, so the runtime guards are in place.
Each provider's `__init__` should raise a clear `ImportError` message like
*"Install gensay[openai] to use the OpenAI provider"*.

### 2b. Pin ruff/ty versions in CI (Low Priority)

`uvx ruff` and `uvx ty` resolve whatever version is current. Pinning
(e.g. `uvx ruff@0.9.x`) avoids surprise lint failures when a new rule is
enabled upstream.

---

## 3. New Features

### 3a. Shell completion scripts (Medium Priority)

`gensay` uses argparse. Generating bash/zsh/fish completions would improve
discoverability. Libraries like `shtab` or `argcomplete` can auto-generate
these from an `ArgumentParser`.

```python
# One-liner with shtab:
# gensay --print-completion bash > /etc/bash_completion.d/gensay
```

### 3b. Configuration file support (Medium Priority)

There's no persistent config file; users must pass flags or set env vars every
time. A `~/.config/gensay/config.toml` (or `$XDG_CONFIG_HOME/gensay/config.toml`
via `platformdirs`, which is already a dependency) could store:

- Default provider
- Default voice per provider
- Default output format
- Cache settings

### 3c. SSML input support (Low Priority)

Amazon Polly and ElevenLabs both support SSML natively. Adding a `--ssml` flag
that passes through raw SSML (skipping the text chunker) would unlock
pronunciation control, pauses, and emphasis for users who need it.

### 3d. Streaming playback (Low Priority)

Currently, audio is fully synthesized before playback begins. For cloud
providers that support streaming (OpenAI, ElevenLabs), piping audio chunks
directly to the audio device would reduce time-to-first-sound, especially for
long texts.

---

## 4. Code Quality and Robustness

### 4a. Structured logging (Medium Priority)

The codebase uses `print(..., file=sys.stderr)` for warnings and diagnostics.
Switching to Python's `logging` module (with a `--verbose` / `--debug` flag)
would let users control verbosity and make troubleshooting easier without
cluttering normal output.

### 4b. Improve async implementation (Medium Priority)

The base class async methods use the deprecated `get_event_loop()` pattern
(`base.py:101,114`). This should use `asyncio.get_running_loop()` or
`asyncio.to_thread()` (Python 3.11+):

```python
async def speak_async(self, text, voice=None, rate=None):
    await asyncio.to_thread(self.speak, text, voice, rate)
```

Providers that have native async clients (OpenAI, ElevenLabs) could override
with true async implementations instead of wrapping sync calls in an executor.

### 4c. Provider health checks (Low Priority)

A `gensay --doctor` command that verifies each provider's prerequisites
(API keys set, ffmpeg available, PortAudio installed, AWS credentials valid)
would make setup and debugging much smoother.

---

## 5. Testing

### 5a. CLI integration tests (Medium Priority)

`test_cli.py` is relatively thin at 67 lines. Expanding it to cover error
paths (bad provider name, missing input, conflicting flags, `--repl` quit,
`--listen` lifecycle) would increase confidence in the user-facing surface.

### 5b. Coverage gating (Low Priority)

With `pytest-cov` already in dev dependencies, adding a minimum coverage
threshold (`--cov-fail-under=80`) in CI would prevent coverage regression.

---

## 6. Documentation

### 6a. Add a CHANGELOG (Medium Priority)

There is no CHANGELOG. As the project approaches 1.0, maintaining a changelog
(or auto-generating one from conventional commits) helps users understand
what changed between releases.

### 6b. Reconcile USAGE.md with actual CLI (Low Priority)

`USAGE.md` lists `-i/--interactive` as "(not implemented)" but the feature
exists as `--repl`. This should be updated to match reality.

---

## Summary: Prioritized Roadmap

| Priority | Enhancement | Effort |
|----------|-------------|--------|
| High | CI test workflow | Small |
| High | Make cloud SDKs optional deps | Medium |
| Medium | Shell completions | Small |
| Medium | Config file support | Medium |
| Medium | Structured logging | Small |
| Medium | Fix async to use `to_thread` | Small |
| Medium | Expand CLI integration tests | Medium |
| Medium | Add CHANGELOG | Small |
| Medium | Lint/typecheck in CI | Small |
| Low | SSML support | Medium |
| Low | Streaming playback | Large |
| Low | Provider health checks (`--doctor`) | Medium |
| Low | Automated release workflow | Medium |
| Low | Coverage gating in CI | Small |
| Low | Reconcile USAGE.md | Small |
| Low | Pin tool versions in CI | Small |
