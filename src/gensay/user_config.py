"""Per-user defaults from XDG/platformdirs config directory.

Precedence for CLI defaults (highest wins):
  1. Explicit CLI flags
  2. Environment variables (GENSAY_*)
  3. User config file (this module)
  4. Built-in platform defaults

Provider secrets (``<provider>.api_key`` keys) are stored in the OS keychain
via the ``keyring`` package — never in the plaintext TOML file. The provider's
own env var (e.g. ELEVENLABS_API_KEY) still takes precedence at runtime.

Config path (override with GENSAY_CONFIG):
  Linux:   $XDG_CONFIG_HOME/gensay/config.toml  (~/.config/gensay/config.toml)
  macOS:   ~/Library/Application Support/gensay/config.toml
  Windows: %APPDATA%\\gensay\\config.toml
"""

from __future__ import annotations

import contextlib
import difflib
import os
import sys
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import platformdirs

from .providers.registry import provider_config_key_types

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
        "no_stream",
        "progress",
        "via_daemon",
        "no_daemon",
        "auto_daemon",
    }
)

# Canonical key → value type for get/set validation
# Nested daemon keys use "daemon.<name>" dotted form.
KEY_TYPES: dict[str, type] = {
    "provider": str,
    "voice": str,
    "rate": int,
    "format": str,
    "chunk_size": int,
    "no_cache": bool,
    "no_progress": bool,
    "no_stream": bool,
    "progress": bool,
    "via_daemon": bool,
    "no_daemon": bool,
    "auto_daemon": bool,
    "daemon.provider": str,
    "daemon.voice": str,
    "daemon.rate": int,
    "daemon.no_cache": bool,
    "daemon.no_preload": bool,
    "daemon.idle_unload_s": float,
    "daemon.idle_exit_s": float,
    "daemon.ready_timeout": float,
    # Provider-scoped keys ("<provider>.api_key", "<provider>.model", ...)
    # are declared on each ProviderSpec in providers/registry.py.
    **provider_config_key_types(),
}

KNOWN_KEYS = tuple(sorted(KEY_TYPES))

KEYRING_SERVICE = "gensay"


def is_secret_key(key: str) -> bool:
    """Keys whose values live in the OS keychain, never the config file."""
    return key.endswith(".api_key")


def _keyring_module():
    try:
        import keyring
    except ImportError as e:
        raise ConfigValueError(
            "secret storage requires the 'keyring' package; "
            "install it with: pip install 'gensay[keychain]' "
            "(also included in the deepgram/elevenlabs extras)"
        ) from e
    return keyring


def get_secret(key: str) -> str | None:
    """Read a secret from the OS keychain; None if unset or backend unavailable."""
    kr = _keyring_module()
    try:
        return kr.get_password(KEYRING_SERVICE, key)
    except kr.errors.KeyringError as e:
        raise ConfigValueError(f"could not read {key!r} from OS keychain: {e}") from e


def set_secret(key: str, value: str) -> None:
    kr = _keyring_module()
    try:
        kr.set_password(KEYRING_SERVICE, key, value)
    except kr.errors.KeyringError as e:
        raise ConfigValueError(f"could not store {key!r} in OS keychain: {e}") from e


def delete_secret(key: str) -> bool:
    """Remove a secret from the OS keychain. Returns True if it was present."""
    kr = _keyring_module()
    try:
        kr.delete_password(KEYRING_SERVICE, key)
    except kr.errors.PasswordDeleteError:
        return False
    except kr.errors.KeyringError as e:
        raise ConfigValueError(f"could not delete {key!r} from OS keychain: {e}") from e
    return True


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
    no_stream: bool | None = None
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
            "no_stream",
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
    if _env_set("GENSAY_NO_STREAM"):
        merged.no_stream = _env_flag("GENSAY_NO_STREAM")
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

# provider = "chatterbox"   # chatterbox | macos | openai | elevenlabs | deepgram | polly | mock
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

# Provider API keys are NOT stored here. They go to the OS keychain:
#   gensay config set elevenlabs.api_key '<your-key>'
# ELEVENLABS_API_KEY env var (or .env) still takes precedence at runtime.
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


class ConfigKeyError(KeyError):
    """Unknown or invalid config key."""


def _unknown_key_error(key: str) -> ConfigKeyError:
    msg = f"unknown key {key!r}; known keys: {', '.join(KNOWN_KEYS)}"
    if matches := difflib.get_close_matches(key, KNOWN_KEYS, n=3, cutoff=0.6):
        msg += f"\ndid you mean: {', '.join(matches)}?"
    return ConfigKeyError(msg)


class ConfigValueError(ValueError):
    """Invalid config value for key type."""


def load_raw_dict(path: Path | None = None) -> dict[str, Any]:
    """Load config file as a plain dict (empty if missing)."""
    cfg_path = path or default_config_path()
    if not cfg_path.is_file():
        return {}
    try:
        raw = cfg_path.read_bytes()
        if not raw.strip():
            return {}
        data = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise ConfigValueError(f"could not read config {cfg_path}: {e}") from e
    if not isinstance(data, dict):
        raise ConfigValueError(f"config root must be a table: {cfg_path}")
    return data


def dump_toml(data: dict[str, Any]) -> str:  # noqa: C901
    """Serialize a simple dict (scalars + one-level tables) to TOML text."""
    lines: list[str] = [
        "# gensay user defaults — managed by `gensay config set|unset`",
        "",
    ]
    # Top-level scalars first (stable order: known keys then extras)
    top_keys = [k for k in KNOWN_KEYS if "." not in k]
    seen: set[str] = set()
    for key in top_keys:
        if key in data and not isinstance(data[key], dict):
            lines.append(f"{key} = {_toml_literal(data[key])}")
            seen.add(key)
    for key in sorted(data):
        if key in seen or isinstance(data[key], dict):
            continue
        lines.append(f"{key} = {_toml_literal(data[key])}")

    # Tables
    tables = {k: v for k, v in data.items() if isinstance(v, dict)}
    # Prefer known daemon table order
    table_names = sorted(tables, key=lambda n: (n != "daemon", n))
    for name in table_names:
        table = tables[name]
        if not table:
            continue
        lines.append("")
        lines.append(f"[{name}]")
        # known daemon keys first
        preferred = [k.split(".", 1)[1] for k in KNOWN_KEYS if k.startswith(f"{name}.")]
        for sub in preferred:
            if sub in table:
                lines.append(f"{sub} = {_toml_literal(table[sub])}")
        for sub in sorted(table):
            if sub not in preferred:
                lines.append(f"{sub} = {_toml_literal(table[sub])}")

    lines.append("")
    return "\n".join(lines)


def _toml_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        # keep ints clean when whole
        if value.is_integer():
            return str(int(value))
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    raise ConfigValueError(f"unsupported config value type: {type(value).__name__}")


def save_raw_dict(data: dict[str, Any], path: Path | None = None) -> Path:
    """Write config dict to TOML (creates parent dirs)."""
    cfg_path = path or default_config_path()
    cfg_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    cfg_path.write_text(dump_toml(data), encoding="utf-8")
    with contextlib.suppress(OSError):
        cfg_path.chmod(0o600)
    return cfg_path


def normalize_key(key: str) -> str:
    """Normalize user key to canonical dotted form."""
    k = key.strip().lower().replace("-", "_")
    if k.startswith("daemon_"):
        k = "daemon." + k[len("daemon_") :]
    return k


def parse_config_value(key: str, raw: str) -> Any:
    """Parse a CLI string into the typed value for ``key``."""
    key = normalize_key(key)
    if key not in KEY_TYPES:
        raise _unknown_key_error(key)
    typ = KEY_TYPES[key]
    text = raw.strip()
    if typ is bool:
        low = text.lower()
        if low in ("1", "true", "yes", "on"):
            return True
        if low in ("0", "false", "no", "off"):
            return False
        raise ConfigValueError(f"{key} expects bool (true/false), got {raw!r}")
    if typ is int:
        try:
            return int(text, 10)
        except ValueError as e:
            raise ConfigValueError(f"{key} expects int, got {raw!r}") from e
    if typ is float:
        try:
            return float(text)
        except ValueError as e:
            raise ConfigValueError(f"{key} expects float, got {raw!r}") from e
    # str
    return text


def get_config_value(
    key: str,
    *,
    path: Path | None = None,
    effective: bool = False,
) -> Any:
    """Read one key from file (or effective file+env if effective=True).

    Returns None if unset. Raises ConfigKeyError for unknown keys.
    """
    key = normalize_key(key)
    if key not in KEY_TYPES:
        raise _unknown_key_error(key)
    if is_secret_key(key):
        return get_secret(key)

    if effective:
        cfg = resolve_user_config(path)
        return _user_config_get(cfg, key)

    data = load_raw_dict(path)
    return _dict_get_dotted(data, key)


def set_config_value(key: str, value: str | Any, *, path: Path | None = None) -> Any:
    """Set one key and persist. ``value`` may be a string (parsed) or typed value."""
    key = normalize_key(key)
    if key not in KEY_TYPES:
        raise _unknown_key_error(key)
    parsed = parse_config_value(key, value) if isinstance(value, str) else value
    # type check
    expected = KEY_TYPES[key]
    if expected is float and isinstance(parsed, int) and not isinstance(parsed, bool):
        parsed = float(parsed)
    elif expected is bool:
        if not isinstance(parsed, bool):
            raise ConfigValueError(f"{key} expects bool")
    elif not isinstance(parsed, expected):
        # allow int for float already handled
        raise ConfigValueError(f"{key} expects {expected.__name__}")

    if is_secret_key(key):
        set_secret(key, parsed)
        return parsed

    data = load_raw_dict(path)
    _dict_set_dotted(data, key, parsed)
    save_raw_dict(data, path)
    return parsed


def unset_config_value(key: str, *, path: Path | None = None) -> bool:
    """Remove one key from file. Returns True if it was present."""
    key = normalize_key(key)
    if key not in KEY_TYPES:
        raise _unknown_key_error(key)
    if is_secret_key(key):
        return delete_secret(key)
    data = load_raw_dict(path)
    removed = _dict_del_dotted(data, key)
    if removed:
        save_raw_dict(data, path)
    return removed


def _dict_get_dotted(data: dict[str, Any], key: str) -> Any:
    if "." not in key:
        return data.get(key)
    table, sub = key.split(".", 1)
    nested = data.get(table)
    if not isinstance(nested, dict):
        return None
    return nested.get(sub)


def _dict_set_dotted(data: dict[str, Any], key: str, value: Any) -> None:
    if "." not in key:
        data[key] = value
        return
    table, sub = key.split(".", 1)
    nested = data.get(table)
    if not isinstance(nested, dict):
        nested = {}
        data[table] = nested
    nested[sub] = value


def _dict_del_dotted(data: dict[str, Any], key: str) -> bool:
    if "." not in key:
        if key in data:
            del data[key]
            return True
        return False
    table, sub = key.split(".", 1)
    nested = data.get(table)
    if not isinstance(nested, dict) or sub not in nested:
        return False
    del nested[sub]
    if not nested:
        del data[table]
    return True


def _user_config_get(cfg: UserConfig, key: str) -> Any:
    if "." not in key:
        return getattr(cfg, key, None)
    table, sub = key.split(".", 1)
    if table != "daemon":
        return None
    return getattr(cfg.daemon, sub, None)
