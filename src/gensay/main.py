#!/usr/bin/env python3
"""gensay - A multi-provider TTS tool compatible with macOS say command."""

from __future__ import annotations

import argparse
import contextlib
import json
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

# Providers with expensive process-local state — prefer daemon when available
WARM_ELIGIBLE_PROVIDERS = frozenset({"chatterbox"})

# Network-dependent providers — get offline fallback to macos `say`
CLOUD_PROVIDERS = frozenset({"elevenlabs", "openai", "polly"})


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


def platform_default_provider() -> str:
    """Built-in provider when nothing else is configured."""
    if sys.platform == "darwin":
        return "macos"
    return "chatterbox"


def get_default_provider(user_provider: str | None = None) -> str:
    """Resolve provider: env/config (via user_provider) > platform default."""
    if user_provider:
        if user_provider in PROVIDER_NAMES:
            return user_provider
        print(
            f"Warning: configured provider '{user_provider}' is not valid. "
            f"Valid providers: {', '.join(PROVIDER_NAMES)}",
            file=sys.stderr,
        )
    return platform_default_provider()


def get_version() -> str:
    """Get the package version from installed metadata."""
    try:
        return get_pkg_version("gensay")
    except Exception:
        return "unknown"


def create_parser(user_cfg=None) -> argparse.ArgumentParser:
    """Create the argument parser matching macOS say command.

    ``user_cfg`` is a UserConfig (file + env layered); its values become argparse defaults
    so bare ``gensay "hi"`` picks them up without flags.
    """
    from .user_config import UserConfig

    cfg: UserConfig = user_cfg or UserConfig()
    d = cfg.main_cli_defaults()
    default_provider = get_default_provider(d.get("provider"))

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
  gensay --provider macos --list-voices # List voices for specific provider
  gensay daemon start -p chatterbox
  gensay daemon status
  gensay daemon stop
  gensay config path | show | init""",
    )

    # Text input options
    parser.add_argument("message", nargs="*", default=[], help="Text message to speak")
    parser.add_argument(
        "-f", "--input-file", dest="file", help='Read text from file (use "-" for stdin)'
    )

    # Voice and rate options
    parser.add_argument(
        "-v",
        "--voice",
        default=d.get("voice"),
        help='Select voice by name (use "?" to list voices)',
    )
    parser.add_argument(
        "-r",
        "--rate",
        type=int,
        default=d.get("rate"),
        help="Speech rate in words per minute",
    )

    # Output options
    parser.add_argument(
        "-o", "--output-file", dest="output", help="Save audio to file instead of playing"
    )
    parser.add_argument(
        "--format",
        choices=[f.value for f in AudioFormat],
        default=d.get("format"),
        help="Audio format for output file",
    )

    # Provider options
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
    # store_true with config default: CLI can only force True; use config/env to default True
    parser.add_argument(
        "--no-cache",
        action="store_true",
        default=bool(d.get("no_cache", False)),
        help="Disable caching",
    )
    parser.add_argument("--clear-cache", action="store_true", help="Clear cache and exit")
    parser.add_argument("--cache-stats", action="store_true", help="Show cache statistics and exit")
    parser.add_argument(
        "--cache-ahead",
        action="store_true",
        help="Pre-cache audio chunks in background (chatterbox only)",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        default=bool(d.get("no_progress", False)),
        help="Disable progress bars",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=int(d.get("chunk_size", 500)),
        help="Text chunk size for processing (default: %(default)s)",
    )

    # Interactive options
    parser.add_argument(
        "--progress",
        action="store_true",
        default=bool(d.get("progress", False)),
        help="Show progress meter",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        "--repl",
        action="store_true",
        dest="repl",
        help="Start interactive REPL mode (provider initialized once, reused for each prompt)",
    )

    # Daemon client routing (BooleanOptionalAction so config default True is overridable)
    parser.add_argument(
        "--via-daemon",
        action=argparse.BooleanOptionalAction,
        default=bool(d.get("via_daemon", False)),
        help="Route request through gensay daemon (fail if daemon not running)",
    )
    parser.add_argument(
        "--no-daemon",
        action="store_true",
        default=bool(d.get("no_daemon", False)),
        help="Force in-process cold path even if daemon is running",
    )
    parser.add_argument(
        "--auto-daemon",
        action=argparse.BooleanOptionalAction,
        default=bool(d.get("auto_daemon", False)),
        help="Auto-start daemon if missing (warm-eligible providers only)",
    )
    parser.add_argument(
        "--listen",
        nargs="?",
        const="",
        metavar="IGNORED",
        help=argparse.SUPPRESS,  # removed; kept only to print migration error
    )

    # Version
    parser.add_argument("--version", action="version", version=f"%(prog)s {get_version()}")

    return parser


def create_daemon_parser(user_cfg=None) -> argparse.ArgumentParser:
    """Parser for `gensay daemon ...` subcommands."""
    from .user_config import UserConfig

    cfg: UserConfig = user_cfg or UserConfig()
    dd = cfg.daemon
    # Top-level provider can fill daemon.provider if daemon section omits it
    daemon_provider = dd.provider or cfg.provider or "chatterbox"
    if daemon_provider not in PROVIDER_NAMES:
        daemon_provider = "chatterbox"

    idle_unload = (
        dd.idle_unload_s
        if dd.idle_unload_s is not None
        else float(os.environ.get("GENSAY_DAEMON_IDLE_UNLOAD_S", "0"))
    )
    idle_exit = (
        dd.idle_exit_s
        if dd.idle_exit_s is not None
        else float(os.environ.get("GENSAY_DAEMON_IDLE_EXIT_S", "0"))
    )
    ready_timeout = (
        dd.ready_timeout
        if dd.ready_timeout is not None
        else float(os.environ.get("GENSAY_DAEMON_START_TIMEOUT_S", "120"))
    )

    parser = argparse.ArgumentParser(
        prog="gensay daemon",
        description="Manage the warm TTS inference daemon",
    )
    sub = parser.add_subparsers(dest="daemon_cmd", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "-p",
            "--provider",
            choices=PROVIDER_NAMES,
            default=daemon_provider,
            help=f"Provider to keep warm (default: {daemon_provider})",
        )
        p.add_argument(
            "-v",
            "--voice",
            default=dd.voice or cfg.voice,
            help="Default voice",
        )
        p.add_argument(
            "-r",
            "--rate",
            type=int,
            default=dd.rate if dd.rate is not None else cfg.rate,
            help="Default speech rate (wpm)",
        )
        p.add_argument(
            "--no-cache",
            action="store_true",
            default=bool(dd.no_cache if dd.no_cache is not None else (cfg.no_cache or False)),
            help="Disable audio disk cache",
        )
        p.add_argument("--socket", help="Unix socket path override")
        p.add_argument("--runtime-dir", help="Runtime directory for socket/pid")
        p.add_argument(
            "--no-preload",
            action="store_true",
            default=bool(dd.no_preload or False),
            help="Do not load model at start (load on first request)",
        )
        p.add_argument(
            "--idle-unload-s",
            type=float,
            default=idle_unload,
            help="Unload model after this many idle seconds (0=never)",
        )
        p.add_argument(
            "--idle-exit-s",
            type=float,
            default=idle_exit,
            help="Exit process after this many idle seconds (0=never)",
        )

    p_start = sub.add_parser("start", help="Start daemon in background and wait until ready")
    add_common(p_start)
    p_start.add_argument(
        "--ready-timeout",
        type=float,
        default=ready_timeout,
        help="Seconds to wait for daemon readiness",
    )

    p_run = sub.add_parser("run", help="Run daemon in foreground (for launchd / debugging)")
    add_common(p_run)

    p_stop = sub.add_parser("stop", help="Stop the running daemon")
    p_stop.add_argument("--socket", help="Unix socket path override")
    p_stop.add_argument("--runtime-dir", help="Runtime directory for socket/pid")

    p_status = sub.add_parser("status", help="Show daemon status")
    p_status.add_argument("--socket", help="Unix socket path override")
    p_status.add_argument("--runtime-dir", help="Runtime directory for socket/pid")
    p_status.add_argument(
        "--json", action="store_true", dest="as_json", help="Machine-readable JSON"
    )

    p_restart = sub.add_parser("restart", help="Stop then start the daemon")
    add_common(p_restart)
    p_restart.add_argument(
        "--ready-timeout",
        type=float,
        default=ready_timeout,
        help="Seconds to wait for daemon readiness",
    )

    return parser


def create_config_parser() -> argparse.ArgumentParser:
    """Parser for `gensay config ...`."""
    parser = argparse.ArgumentParser(
        prog="gensay config",
        description="Manage per-user gensay defaults (XDG/platformdirs config dir)",
    )
    sub = parser.add_subparsers(dest="config_cmd", required=True)
    sub.add_parser("path", help="Print config file path")
    p_show = sub.add_parser("show", help="Show effective defaults (file + env)")
    p_show.add_argument("--json", action="store_true", dest="as_json", help="JSON output")
    p_show.add_argument(
        "--file-only",
        action="store_true",
        help="Show file contents only (ignore env overrides)",
    )
    p_init = sub.add_parser("init", help="Write example config.toml")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing config file")

    p_get = sub.add_parser("get", help="Get a single key from config file")
    p_get.add_argument("key", help="Key (e.g. provider, auto_daemon, daemon.provider)")
    p_get.add_argument(
        "--effective",
        action="store_true",
        help="Resolve file + env (not file alone)",
    )
    p_get.add_argument(
        "--default",
        dest="default_value",
        default=None,
        help="Print this if key is unset (exit 0); otherwise exit 1 when unset",
    )

    p_set = sub.add_parser("set", help="Set a key and write config.toml")
    p_set.add_argument("key", help="Key (e.g. provider, auto_daemon, daemon.provider)")
    p_set.add_argument(
        "value",
        nargs="+",
        help="Value (bool: true/false; join multiple words with spaces for strings)",
    )

    p_unset = sub.add_parser("unset", help="Remove a key from config.toml")
    p_unset.add_argument("key", help="Key to remove")

    sub.add_parser("keys", help="List known config keys")
    return parser


def get_text_input(args) -> str:
    """Get text input from command line arguments."""
    if args.message and args.file:
        print("Error: Cannot specify both message and -f option", file=sys.stderr)
        sys.exit(1)

    if args.message:
        return " ".join(args.message)
    elif args.file:
        if args.file == "-":
            return sys.stdin.read().strip()
        else:
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

        for voice in voices:
            display_name = voice.get("name", voice["id"])
            lang = voice.get("language", "Unknown")
            desc = voice.get("description", "")

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
        print()


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


def _should_use_daemon(args, provider_name: str) -> str:
    """Return 'require' | 'prefer' | 'never' for daemon routing.

    Flag defaults already include file+env layering; only read args here.
    """
    if getattr(args, "no_daemon", False):
        return "never"
    if getattr(args, "via_daemon", False):
        return "require"
    if provider_name in WARM_ELIGIBLE_PROVIDERS:
        return "prefer"
    return "never"


def _daemon_paths_from_args(args):
    from .daemon.paths import default_paths

    return default_paths(
        runtime_dir=getattr(args, "runtime_dir", None),
        socket=getattr(args, "socket", None),
    )


def _try_daemon_speak_or_save(args, text: str) -> bool:  # noqa: C901
    """Attempt speak/save via daemon. Returns True if handled (success). Raises on require failure."""
    from .daemon.client import DaemonClient, DaemonClientError, DaemonNotRunning, DaemonRPCError
    from .daemon.lifecycle import LifecycleError, start_detached
    from .daemon.paths import default_paths

    mode = _should_use_daemon(args, args.provider)
    if mode == "never":
        return False

    paths = default_paths()
    client = DaemonClient(paths)
    auto = bool(getattr(args, "auto_daemon", False))

    if not client.is_running():
        if auto and args.provider in WARM_ELIGIBLE_PROVIDERS:
            try:
                start_detached(
                    args.provider,
                    paths=paths,
                    voice=args.voice,
                    rate=args.rate,
                    preload=True,
                    no_cache=args.no_cache,
                )
            except (LifecycleError, DaemonNotRunning) as e:
                if mode == "require":
                    print(f"Error: failed to auto-start daemon: {e}", file=sys.stderr)
                    sys.exit(1)
                print(f"Warning: auto-start daemon failed ({e}); using cold path", file=sys.stderr)
                return False
        elif mode == "require":
            print(
                f"Error: daemon not running (socket {paths.socket}). "
                f"Start with: gensay daemon start -p {args.provider}",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            if args.provider in WARM_ELIGIBLE_PROVIDERS:
                print(
                    f"hint: start a warm daemon to skip model load: "
                    f"gensay daemon start -p {args.provider}",
                    file=sys.stderr,
                )
            return False

    try:
        if args.list_voices:
            voices = client.list_voices()
            # print like list_voices()
            print(f"\nVoices for provider: {args.provider} (via daemon)\n")
            for voice in voices:
                display_name = voice.get("name", voice["id"])
                lang = voice.get("language", "Unknown")
                desc = voice.get("description", "")
                if desc:
                    print(f"{display_name:<20} {lang:<10} # {desc}")
                else:
                    print(f"{display_name:<20} {lang:<10}")
            return True

        if args.output:
            result = client.save(
                text,
                args.output,
                voice=args.voice,
                rate=args.rate,
                format=args.format,
                no_cache=args.no_cache,
                provider=args.provider,
            )
            print(f"Audio saved to {result.path or args.output}")
        else:
            client.speak(
                text,
                voice=args.voice,
                rate=args.rate,
                no_cache=args.no_cache,
                provider=args.provider,
            )
        return True
    except DaemonRPCError as e:
        print(f"Error: daemon RPC failed: {e}", file=sys.stderr)
        sys.exit(1)
    except DaemonNotRunning:
        if mode == "require":
            print("Error: daemon disappeared mid-request", file=sys.stderr)
            sys.exit(1)
        return False
    except DaemonClientError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def config_main(argv: list[str] | None = None) -> None:  # noqa: C901
    """Entry for `gensay config ...`."""
    parser = create_config_parser()
    args = parser.parse_args(argv)

    from .user_config import (
        KNOWN_KEYS,
        ConfigKeyError,
        ConfigValueError,
        default_config_path,
        get_config_value,
        load_user_config,
        resolve_user_config,
        set_config_value,
        unset_config_value,
        write_example_config,
    )

    if args.config_cmd == "path":
        print(default_config_path())
        return

    if args.config_cmd == "keys":
        for key in KNOWN_KEYS:
            print(key)
        return

    if args.config_cmd == "show":
        cfg = load_user_config() if args.file_only else resolve_user_config()
        data = cfg.as_public_dict()
        from .user_config import get_secret, is_secret_key

        try:
            secrets = sorted(
                k for k in KNOWN_KEYS if is_secret_key(k) and get_secret(k) is not None
            )
        except ConfigValueError:
            secrets = []  # keyring unavailable
        meta = {
            "path": str(cfg.path) if cfg.path else None,
            "exists": bool(cfg.path and cfg.path.is_file()),
            "loaded": cfg.loaded,
        }
        if args.as_json:
            print(
                json.dumps(
                    {"meta": meta, "defaults": data, "secrets_in_keychain": secrets}, indent=2
                )
            )
        else:
            print(f"path: {meta['path']}")
            print(f"exists: {meta['exists']}")
            print(f"loaded: {meta['loaded']}")
            if not data:
                print("(no defaults set)")
            else:
                print("defaults:")
                for k, v in data.items():
                    if k == "daemon" and isinstance(v, dict):
                        print("  [daemon]")
                        for dk, dv in v.items():
                            print(f"    {dk} = {dv!r}")
                    else:
                        print(f"  {k} = {v!r}")
            for k in secrets:
                print(f"  {k} = (stored in OS keychain)")
        return

    if args.config_cmd == "init":
        try:
            path = write_example_config(force=args.force)
        except FileExistsError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"wrote {path}")
        return

    if args.config_cmd == "get":
        try:
            val = get_config_value(args.key, effective=args.effective)
        except ConfigKeyError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except ConfigValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        if val is None:
            if args.default_value is not None:
                print(args.default_value)
                return
            print(f"Error: key {args.key!r} is not set", file=sys.stderr)
            sys.exit(1)
        if isinstance(val, bool):
            print("true" if val else "false")
        else:
            print(val)
        return

    if args.config_cmd == "set":
        raw = " ".join(args.value)
        try:
            parsed = set_config_value(args.key, raw)
        except (ConfigKeyError, ConfigValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        from .user_config import is_secret_key

        if is_secret_key(args.key):
            print(f"set {args.key} (stored in OS keychain)")
            return
        path = default_config_path()
        shown = ("true" if parsed else "false") if isinstance(parsed, bool) else parsed
        print(f"set {args.key} = {shown}")
        print(f"wrote {path}")
        return

    if args.config_cmd == "unset":
        try:
            removed = unset_config_value(args.key)
        except ConfigKeyError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except ConfigValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        if removed:
            from .user_config import is_secret_key

            print(f"unset {args.key}")
            if not is_secret_key(args.key):
                print(f"wrote {default_config_path()}")
        else:
            print(f"key {args.key!r} was not set", file=sys.stderr)
            sys.exit(1)
        return

    parser.error(f"unknown config command: {args.config_cmd}")


def daemon_main(argv: list[str] | None = None) -> None:
    """Entry for `gensay daemon ...`."""
    from dotenv import load_dotenv

    load_dotenv()

    from .user_config import resolve_user_config

    user_cfg = resolve_user_config()
    parser = create_daemon_parser(user_cfg)
    args = parser.parse_args(argv)

    from .daemon import lifecycle
    from .daemon.paths import default_paths
    from .daemon.server import run_server

    paths = default_paths(
        runtime_dir=getattr(args, "runtime_dir", None),
        socket=getattr(args, "socket", None),
    )

    if args.daemon_cmd == "status":
        st = lifecycle.status(paths)
        if getattr(args, "as_json", False):
            print(json.dumps(st, indent=2))
        else:
            if st.get("running"):
                print(
                    f"running: yes\n"
                    f"  pid: {st.get('pid')}\n"
                    f"  provider: {st.get('provider')}\n"
                    f"  model_loaded: {st.get('model_loaded')}\n"
                    f"  device: {st.get('device')}\n"
                    f"  uptime_s: {st.get('uptime_s')}\n"
                    f"  queue_depth: {st.get('queue_depth')}\n"
                    f"  idle_s: {st.get('idle_s')}\n"
                    f"  version: {st.get('version')}\n"
                    f"  socket: {st.get('socket')}"
                )
            else:
                print(f"running: no\n  socket: {st.get('socket')}\n  pidfile_pid: {st.get('pid')}")
                if st.get("note"):
                    print(f"  note: {st['note']}")
        return

    if args.daemon_cmd == "stop":
        lifecycle.stop(paths)
        print("daemon stopped")
        return

    if args.daemon_cmd == "restart":
        with contextlib.suppress(Exception):
            lifecycle.stop(paths)
        args.daemon_cmd = "start"
        # fall through to start

    if args.daemon_cmd == "start":
        try:
            st = lifecycle.start_detached(
                args.provider,
                paths=paths,
                voice=args.voice,
                rate=args.rate,
                preload=not args.no_preload,
                idle_unload_s=args.idle_unload_s,
                idle_exit_s=args.idle_exit_s,
                no_cache=args.no_cache,
                ready_timeout_s=args.ready_timeout,
            )
        except Exception as e:
            print(f"Error starting daemon: {e}", file=sys.stderr)
            sys.exit(1)
        print(
            f"started gensay daemon pid={st.pid} provider={st.provider} "
            f"model_loaded={st.model_loaded}\nsocket={paths.socket}"
        )
        return

    if args.daemon_cmd == "run":
        config = TTSConfig(
            voice=args.voice,
            rate=args.rate,
            cache_enabled=not args.no_cache,
            extra={"show_progress": False, "chunk_size": 500},
        )
        run_server(
            args.provider,
            config=config,
            paths=paths,
            preload=not args.no_preload,
            idle_unload_s=args.idle_unload_s,
            idle_exit_s=args.idle_exit_s,
        )
        return

    parser.error(f"unknown daemon command: {args.daemon_cmd}")


def main():  # noqa: C901
    """Main entry point."""
    # Route subcommands before the macOS-say-compatible parser
    if len(sys.argv) > 1 and sys.argv[1] == "daemon":
        daemon_main(sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "config":
        config_main(sys.argv[2:])
        return

    from dotenv import load_dotenv

    load_dotenv()

    from .user_config import resolve_user_config

    user_cfg = resolve_user_config()
    parser = create_parser(user_cfg)
    args = parser.parse_args()

    # --listen removed in favor of daemon
    if args.listen is not None:
        print(
            "Error: --listen was removed. Use the warm daemon instead:\n"
            "  gensay daemon start -p chatterbox\n"
            "  gensay daemon run -p mock          # foreground\n"
            "  gensay daemon status | stop",
            file=sys.stderr,
        )
        sys.exit(2)

    if handle_cache_operations(args):
        return

    if args.voice == "?":
        args.list_voices = True
        args.voice = None

    needs_text = not (args.list_voices or args.repl)
    text = get_text_input(args) if needs_text else ""
    if needs_text and not text:
        parser.print_usage()
        sys.exit(1)

    # Prefer daemon for speak/save/list_voices when appropriate
    if not args.repl and not args.cache_ahead and _try_daemon_speak_or_save(args, text):
        return

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

    # Provider-scoped config: "<provider>.api_key" from OS keychain (never the file),
    # other "<provider>.<sub>" keys from config.toml → TTSConfig.extra.
    from .user_config import KNOWN_KEYS, get_config_value, get_secret, is_secret_key

    for cfg_key in KNOWN_KEYS:
        if not cfg_key.startswith(prefix := f"{args.provider}."):
            continue
        sub = cfg_key[len(prefix) :]
        if is_secret_key(cfg_key):
            # Providers check their own env var (e.g. ELEVENLABS_API_KEY) first
            with contextlib.suppress(Exception):
                if secret := get_secret(cfg_key):
                    config.extra[sub] = secret
        elif (val := get_config_value(cfg_key)) is not None:
            config.extra[sub] = val

    if args.provider == "chatterbox":
        print(
            "Note: Chatterbox generation is slow on most consumer hardware, "
            "but audio outputs will be cached for re-use.",
            file=sys.stderr,
        )

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

    # Offline resilience: network-dependent providers fall back to local `say`
    if args.provider in CLOUD_PROVIDERS and sys.platform == "darwin":
        from dataclasses import replace

        from .fallback import NetworkFallbackProvider

        provider = NetworkFallbackProvider(
            provider,
            lambda: providers["macos"](replace(config, voice=None)),
            primary_name=args.provider,
        )

    if args.list_voices:
        list_voices(provider)
        return

    if args.repl:
        run_repl(provider, args.voice, args.rate)
        return

    try:
        if args.cache_ahead and isinstance(provider, providers["chatterbox"]):
            print("Pre-caching audio chunks...")
            provider.cache_ahead(text, args.voice, args.rate)
            print("Cache-ahead started in background")

        if args.output:
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
