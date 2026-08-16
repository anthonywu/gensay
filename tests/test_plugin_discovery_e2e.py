"""End-to-end plugin discovery through real importlib.metadata.

The unit tests in test_provider_registry.py exercise discover_plugin_specs
with injected fake entry points. These tests build a real installed
distribution (package + .dist-info with entry_points.txt) on a temp
sys.path and run gensay in fresh subprocesses, proving the whole chain:
metadata scan -> spec registration -> CLI choices -> provider execution.

Subprocesses are required: the registry materializes SPECS at import time,
so an already-imported gensay in this process would not see the plugin.
"""

import os
import subprocess
import sys
import textwrap

import pytest

PLUGIN_NAME = "e2eplug"


def _make_dist(site_dir, *, broken: bool = False) -> None:
    """Create an importable package + real .dist-info under site_dir."""
    pkg = site_dir / PLUGIN_NAME
    pkg.mkdir(parents=True)
    if broken:
        (pkg / "__init__.py").write_text("raise RuntimeError('boom at import')\n")
    else:
        (pkg / "__init__.py").write_text(
            textwrap.dedent(
                f"""
                from gensay.plugin import ProviderSpec

                GENSAY_PROVIDER_SPEC = ProviderSpec(
                    name="{PLUGIN_NAME}",
                    class_name="E2EProvider",
                    module="{PLUGIN_NAME}.provider",
                    kind="test",
                )
                """
            )
        )
        (pkg / "provider.py").write_text(
            textwrap.dedent(
                """
                from pathlib import Path
                from typing import Any

                from gensay.plugin import AudioFormat, TTSProvider


                class E2EProvider(TTSProvider):
                    def speak(self, text, voice=None, rate=None):
                        print(f"E2E-SPOKE:{text}")

                    def save_to_file(self, text, output_path, voice=None, rate=None, format=None):
                        path = Path(output_path)
                        path.write_text(text)
                        return path

                    def list_voices(self) -> list[dict[str, Any]]:
                        return [{"id": "e2e-voice", "name": "E2E Voice", "language": "en-US"}]

                    def get_supported_formats(self):
                        return list(AudioFormat)
                """
            )
        )

    dist_info = site_dir / f"{PLUGIN_NAME}-0.1.0.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {PLUGIN_NAME}\nVersion: 0.1.0\n"
    )
    (dist_info / "entry_points.txt").write_text(
        f"[gensay.providers]\n{PLUGIN_NAME} = {PLUGIN_NAME}:GENSAY_PROVIDER_SPEC\n"
    )
    (dist_info / "RECORD").write_text("")


def _run(args, site_dir, **kwargs):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(site_dir) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, *args], env=env, capture_output=True, text=True, timeout=60, **kwargs
    )


@pytest.fixture
def plugin_site(tmp_path):
    site = tmp_path / "site"
    _make_dist(site)
    return site


@pytest.fixture
def broken_plugin_site(tmp_path):
    site = tmp_path / "site"
    _make_dist(site, broken=True)
    return site


class TestRealMetadataDiscovery:
    def test_registry_sees_plugin(self, plugin_site):
        code = (
            "from gensay.providers.registry import SPECS_BY_NAME; "
            f"spec = SPECS_BY_NAME['{PLUGIN_NAME}']; "
            "assert spec.kind == 'test', spec; "
            "cls = spec.load(); "
            "assert cls.__name__ == 'E2EProvider', cls"
        )
        result = _run(["-c", code], plugin_site)
        assert result.returncode == 0, result.stderr

    def test_cli_offers_plugin_as_provider_choice(self, plugin_site):
        result = _run(["-m", "gensay", "--help"], plugin_site)
        assert result.returncode == 0, result.stderr
        assert PLUGIN_NAME in result.stdout

    def test_cli_executes_plugin_provider(self, plugin_site):
        result = _run(
            ["-m", "gensay", "--provider", PLUGIN_NAME, "hello from the plugin"], plugin_site
        )
        assert result.returncode == 0, result.stderr
        assert "E2E-SPOKE:hello from the plugin" in result.stdout

    def test_cli_lists_plugin_voices(self, plugin_site):
        result = _run(["-m", "gensay", "--provider", PLUGIN_NAME, "--list-voices"], plugin_site)
        assert result.returncode == 0, result.stderr
        assert "E2E Voice" in result.stdout


class TestRealMetadataBrokenPlugin:
    def test_broken_plugin_warns_but_cli_still_works(self, broken_plugin_site):
        result = _run(["-m", "gensay", "--provider", "mock", "still alive"], broken_plugin_site)
        assert result.returncode == 0, result.stderr
        assert PLUGIN_NAME in result.stderr  # skipped-with-warning
        assert PLUGIN_NAME not in result.stdout.split("--provider")[-1][:200]
