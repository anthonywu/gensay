"""Nox test matrix across supported Python versions (matches pyproject classifiers 3.11-3.15)."""

from __future__ import annotations

import subprocess

import nox

nox.options.default_venv_backend = "uv"
nox.options.sessions = ["tests"]

PYTHON_VERSIONS = ["3.11", "3.12", "3.13", "3.14", "3.15"]

# Light install profile for the matrix: no torch (~2 GB per env). The heavy
# chatterbox suite needs torch and is excluded, mirroring CI runs.
TEST_ARGS = [
    "-q",
    "--ignore=tests/test_chatterbox_provider.py",
]


def _portaudio_env() -> dict[str, str]:
    """pyaudio builds from source on interpreters without wheels (e.g. 3.15);
    mirror justfile's portaudio include/lib discovery so the build finds it."""
    prefix = ""
    for probe in (["nix-build", "<nixpkgs>", "-A", "portaudio", "--no-out-link"],):
        try:
            out = subprocess.run(probe, capture_output=True, text=True, timeout=20)
            if out.returncode == 0 and out.stdout.strip():
                prefix = out.stdout.strip().splitlines()[0]
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    if not prefix:
        try:
            out = subprocess.run(
                ["brew", "--prefix", "portaudio"], capture_output=True, text=True, timeout=10
            )
            if out.returncode == 0:
                prefix = out.stdout.strip()
        except FileNotFoundError:
            pass
    if not prefix:
        return {}
    return {"C_INCLUDE_PATH": f"{prefix}/include", "LIBRARY_PATH": f"{prefix}/lib"}


@nox.session(python=PYTHON_VERSIONS)
def tests(session: nox.Session) -> None:
    session.env.update(_portaudio_env())
    session.install("pytest", ".[elevenlabs]")
    session.run("pytest", *TEST_ARGS, *session.posargs)
