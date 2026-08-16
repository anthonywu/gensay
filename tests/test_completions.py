"""Tests for shell completion script generation (`gensay completions`)."""

import shutil
import subprocess

import pytest

from gensay.completions import SHELLS, build_spec, completions_main, render
from gensay.main import PROVIDER_NAMES, _print_voice_names
from gensay.user_config import KNOWN_KEYS


def test_spec_covers_cli_surface():
    spec = build_spec()
    main_flags = [s for o in spec.main_opts for s in o.strings]
    assert "--provider" in main_flags
    assert "--list-voices" in main_flags
    assert "--print-voice-names" not in main_flags  # hidden helper stays hidden
    assert "--listen" not in main_flags  # SUPPRESS'd flags stay hidden

    assert {c.name for c in spec.daemon_cmds} == {"start", "run", "stop", "status", "restart"}
    assert {c.name for c in spec.config_cmds} == {
        "path",
        "show",
        "init",
        "get",
        "set",
        "unset",
        "keys",
    }
    assert all(c.key_positional for c in spec.config_cmds if c.name in ("get", "set", "unset"))
    assert spec.config_keys == tuple(KNOWN_KEYS)


@pytest.mark.parametrize("shell", SHELLS)
def test_render_contains_registry_values(shell):
    script = render(shell)
    for provider in PROVIDER_NAMES:
        assert provider in script
    for key in ("daemon.provider", "provider", "voice"):
        assert key in script
    # daemon + config subcommands present
    for token in ("start", "restart", "status", "unset", "keys"):
        assert token in script
    # dynamic voice helper wired in
    assert "--print-voice-names" in script


@pytest.mark.parametrize("shell", SHELLS)
def test_script_syntax(shell):
    """Each generated script must parse in its target shell (if installed)."""
    exe = shutil.which(shell)
    if exe is None:
        pytest.skip(f"{shell} not installed")
    result = subprocess.run(
        [exe, "-n", "/dev/stdin"],
        input=render(shell),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not installed")
@pytest.mark.parametrize(
    ("words", "expected", "unexpected"),
    [
        (["gensay", "-p", ""], set(PROVIDER_NAMES), set()),
        (["gensay", "--format", ""], {"wav", "mp3"}, {"macos"}),
        (["gensay", "config", ""], {"get", "set", "keys"}, {"start"}),
        (["gensay", "config", "set", ""], {"provider", "daemon.provider"}, {"get"}),
        (["gensay", "daemon", ""], {"start", "stop", "status"}, {"keys"}),
        (["gensay", "daemon", "start", "--"], {"--provider", "--socket"}, {"--format"}),
        (["gensay", "completions", ""], set(SHELLS), set()),
        (["gensay", "--"], {"--provider", "--list-voices", "--via-daemon"}, set()),
    ],
)
def test_bash_functional_completion(words, expected, unexpected):
    """Drive the bash completion function directly and check COMPREPLY."""
    quoted = " ".join(f"'{w}'" for w in words)
    harness = f"""
source /dev/stdin <<'GENSAY_COMPLETION'
{render("bash")}
GENSAY_COMPLETION
COMP_WORDS=({quoted})
COMP_CWORD={len(words) - 1}
_gensay
printf '%s\\n' "${{COMPREPLY[@]}}"
"""
    result = subprocess.run(["bash", "-c", harness], capture_output=True, text=True, check=True)
    completions = set(result.stdout.split())
    assert expected <= completions, f"missing {expected - completions} in {completions}"
    assert not (unexpected & completions)


def test_completions_main_prints_script(capsys):
    completions_main(["zsh"])
    out = capsys.readouterr().out
    assert out.startswith("#compdef gensay")


def test_completions_main_rejects_unknown_shell(capsys):
    with pytest.raises(SystemExit):
        completions_main(["powershell"])


def test_print_voice_names_mock(capsys):
    _print_voice_names("mock")
    out = capsys.readouterr().out
    assert "Mock Voice 1" in out


def test_print_voice_names_swallows_errors(capsys):
    _print_voice_names("no-such-provider")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
