"""Per-user defaults from XDG/platformdirs config directory.

Precedence for CLI defaults (highest wins):
  1. Explicit CLI flags
  2. Environment variables (GENSAY_*)
  3. User config file (this module)
  4. Built-in platform defaults

Config path (override with GENSAY_CONFIG):
  Linux:   $XDG_CONFIG_HOME/gensay/config.toml  (~/.config/gensay/config.toml)
  macOS:   ~/Library/Application Support/gensay/config.toml
  Windows: %APPDATA%\\gensay\\config.toml
"""

from __future__ import annotations

import contextlib
import os
import sys
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import platformdirs

CONFIG_FILENAME = "config.toml"

# Keys that map 1:1 onto argparse dest names for the main CLI
MAIN_CLI_KEYS = frozenset(
    {
        "provider",
        "voice",
        "rate",
        "format",
        "chunk_size",
        "no_cache",
        "no_progress",
        "progress",
        "via_daemon",
        "no_daemon",
        "auto_daemon",
    }
)


@dataclass
class DaemonDefaults:
    """Defaults applied to `gensay daemon start|run|restart` when flags omitted."""

    provider: str | None = None
    voice: str | None = None
    rate: int | None = None
    no_cache: bool | None = None
    no_preload: bool | None = None
    idle_unload_s: float | None = None
    idle_exit_s: float | None = None
    ready_timeout: float | None = None


@dataclass
class UserConfig:
    """User-level defaults for bare `gensay` invocations."""

    provider: str | None = None
    voice: str | None = None
    rate: int | None = None
    format: str | None = None
    chunk_size: int | None = None
    no_cache: bool | None = None
    no_progress: bool | None = None
    progress: bool | None = None
    via_daemon: bool | None = None
    no_daemon: bool | None = None
    auto_daemon: bool | None = None
    daemon: DaemonDefaults = field(default_factory=DaemonDefaults)

    # Metadata (not written back as settings)
    path: Path | None = field(default=None, repr=False, compare=False)
    loaded: bool = field(default=False, repr=False, compare=False)

    def main_cli_defaults(self) -> dict[str, Any]:
        """Argparse defaults for the speak CLI (omit unset keys)."""
        out: dict[str, Any] = {}
        for key in MAIN_CLI_KEYS:
            val = getattr(self, key)
            if val is not None:
                out[key] = val
        return out

    def as_public_dict(self) -> dict[str, Any]:
        """Serializable view (no path/loaded)."""
        d: dict[str, Any] = {}
        for f in fields(self):
            if f.name in ("path", "loaded"):
                continue
            val = getattr(self, f.name)
            if f.name == "daemon":
                dd = {k: v for k, v in asdict(val).items() if v is not None}
                if dd:
                    d["daemon"] = dd
            elif val is not None:
                d[f.name] = val
        return d


def config_dir() -> Path:
    return Path(platformdirs.user_config_dir("gensay", "gensay"))


def default_config_path() -> Path:
    if env := os.environ.get("GENSAY_CONFIG"):
        return Path(env)
    return config_dir() / CONFIG_FILENAME


def load_user_config(path: Path | None = None) -> UserConfig:
    """Load config from disk; missing/empty file yields empty UserConfig."""
    cfg_path = path or default_config_path()
    cfg = UserConfig(path=cfg_path)
    if not cfg_path.is_file():
        return cfg
    try:
        raw = cfg_path.read_bytes()
        if not raw.strip():
            return cfg
        data = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        print(f"Warning: could not read config {cfg_path}: {e}", file=sys.stderr)
        return cfg
    if not isinstance(data, dict):
        print(f"Warning: config root must be a table: {cfg_path}", file=sys.stderr)
        return cfg
    return _from_dict(data, cfg_path)


def _from_dict(data: dict[str, Any], path: Path) -> UserConfig:  # noqa: C901
    kwargs: dict[str, Any] = {"path": path, "loaded": True}
    for key in MAIN_CLI_KEYS:
        if key not in data:
            continue
        val = data[key]
        if key in ("rate", "chunk_size") and val is not None:
            kwargs[key] = int(val)
        elif key in (
            "no_cache",
            "no_progress",
            "progress",
            "via_daemon",
            "no_daemon",
            "auto_daemon",
        ):
            kwargs[key] = bool(val)
        elif (
            key == "provider" and val is not None or key in ("voice", "format") and val is not None
        ):
            kwargs[key] = str(val)
        else:
            kwargs[key] = val

    daemon_raw = data.get("daemon")
    if isinstance(daemon_raw, dict):
        dd: dict[str, Any] = {}
        if "provider" in daemon_raw and daemon_raw["provider"] is not None:
            dd["provider"] = str(daemon_raw["provider"])
        if "voice" in daemon_raw and daemon_raw["voice"] is not None:
            dd["voice"] = str(daemon_raw["voice"])
        if "rate" in daemon_raw and daemon_raw["rate"] is not None:
            dd["rate"] = int(daemon_raw["rate"])
        for bkey in ("no_cache", "no_preload"):
            if bkey in daemon_raw and daemon_raw[bkey] is not None:
                dd[bkey] = bool(daemon_raw[bkey])
        for fkey in ("idle_unload_s", "idle_exit_s", "ready_timeout"):
            if fkey in daemon_raw and daemon_raw[fkey] is not None:
                dd[fkey] = float(daemon_raw[fkey])
        kwargs["daemon"] = DaemonDefaults(**dd)

    return UserConfig(**kwargs)


def apply_env_overrides(cfg: UserConfig) -> UserConfig:  # noqa: C901
    """Return a copy-like config with GENSAY_* env vars layered on top of file values."""
    # Mutate a fresh instance so callers can still inspect file-only state if needed
    merged = UserConfig(
        provider=cfg.provider,
        voice=cfg.voice,
        rate=cfg.rate,
        format=cfg.format,
        chunk_size=cfg.chunk_size,
        no_cache=cfg.no_cache,
        no_progress=cfg.no_progress,
        progress=cfg.progress,
        via_daemon=cfg.via_daemon,
        no_daemon=cfg.no_daemon,
        auto_daemon=cfg.auto_daemon,
        daemon=DaemonDefaults(**asdict(cfg.daemon)),
        path=cfg.path,
        loaded=cfg.loaded,
    )

    if (p := os.environ.get("GENSAY_PROVIDER")) and p.strip():
        merged.provider = p.strip()
    if (v := os.environ.get("GENSAY_VOICE")) and v.strip():
        merged.voice = v.strip()
    if (r := os.environ.get("GENSAY_RATE")) and r.strip():
        with contextlib.suppress(ValueError):
            merged.rate = int(r)
    if (fmt := os.environ.get("GENSAY_FORMAT")) and fmt.strip():
        merged.format = fmt.strip()

    if _env_set("GENSAY_NO_CACHE"):
        merged.no_cache = _env_flag("GENSAY_NO_CACHE")
    if _env_set("GENSAY_VIA_DAEMON"):
        merged.via_daemon = _env_flag("GENSAY_VIA_DAEMON")
    if _env_set("GENSAY_NO_DAEMON"):
        merged.no_daemon = _env_flag("GENSAY_NO_DAEMON")
    if _env_set("GENSAY_AUTO_DAEMON"):
        merged.auto_daemon = _env_flag("GENSAY_AUTO_DAEMON")

    # Daemon section env
    if (p := os.environ.get("GENSAY_DAEMON_PROVIDER")) and p.strip():
        merged.daemon.provider = p.strip()
    if _env_set("GENSAY_DAEMON_IDLE_UNLOAD_S"):
        with contextlib.suppress(ValueError):
            merged.daemon.idle_unload_s = float(os.environ["GENSAY_DAEMON_IDLE_UNLOAD_S"])
    if _env_set("GENSAY_DAEMON_IDLE_EXIT_S"):
        with contextlib.suppress(ValueError):
            merged.daemon.idle_exit_s = float(os.environ["GENSAY_DAEMON_IDLE_EXIT_S"])
    if _env_set("GENSAY_DAEMON_START_TIMEOUT_S"):
        with contextlib.suppress(ValueError):
            merged.daemon.ready_timeout = float(os.environ["GENSAY_DAEMON_START_TIMEOUT_S"])

    return merged


def _env_set(name: str) -> bool:
    return name in os.environ and os.environ[name].strip() != ""


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


EXAMPLE_CONFIG = """\
# gensay user defaults
# Path: resolved via platformdirs user_config_dir (XDG on Linux).
# Override path with GENSAY_CONFIG=/path/to/config.toml
#
# Precedence: CLI flags > environment (GENSAY_*) > this file > built-ins

# provider = "chatterbox"   # chatterbox | macos | openai | elevenlabs | polly | mock
# voice = "default"
# rate = 150
# format = "m4a"            # aiff wav m4a mp3 caf flac aac ogg
# chunk_size = 500
# no_cache = false
# no_progress = false
# progress = false
# via_daemon = false
# no_daemon = false
# auto_daemon = false       # auto-start warm daemon for chatterbox if not running

# [daemon]
# provider = "chatterbox"   # default for `gensay daemon start`
# voice = "default"
# rate = 150
# no_cache = false
# no_preload = false
# idle_unload_s = 0
# idle_exit_s = 0
# ready_timeout = 120
"""


def write_example_config(path: Path | None = None, *, force: bool = False) -> Path:
    """Write example config.toml; refuse to overwrite unless force=True."""
    cfg_path = path or default_config_path()
    cfg_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if cfg_path.exists() and not force:
        raise FileExistsError(f"config already exists: {cfg_path} (use --force to overwrite)")
    cfg_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    with contextlib.suppress(OSError):
        cfg_path.chmod(0o600)
    return cfg_path


def resolve_user_config(path: Path | None = None) -> UserConfig:
    """Load file then apply env overrides — ready for argparse defaults."""
    return apply_env_overrides(load_user_config(path))
