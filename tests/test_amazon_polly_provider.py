"""Tests for Amazon Polly TTS provider."""

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from gensay.providers import AmazonPollyProvider, AudioFormat, TTSConfig

# Directory for test artifacts (git-ignored)
ARTIFACTS_DIR = Path(__file__).parent / "artifacts"


@pytest.fixture(scope="module", autouse=True)
def setup_artifacts_dir():
    """Create artifacts directory if it doesn't exist."""
    ARTIFACTS_DIR.mkdir(exist_ok=True)


def has_aws_credentials() -> bool:
    """Check if AWS credentials are available."""
    # First try aws sts get-caller-identity (handles SSO, IAM roles, etc.)
    try:
        result = subprocess.run(
            ["aws", "sts", "get-caller-identity"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    # Fallback: check env vars
    return bool(os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"))


@pytest.mark.skipif(not has_aws_credentials(), reason="AWS credentials not configured")
class TestAmazonPollyProvider:
    """Test Amazon Polly provider functionality with real API."""

    def test_provider_initialization(self):
        """Test provider initializes with credentials."""
        config = TTSConfig()
        provider = AmazonPollyProvider(config)
        assert provider.client is not None

    def test_list_voices(self):
        """Test listing available voices."""
        config = TTSConfig()
        provider = AmazonPollyProvider(config)

        voices = provider.list_voices()
        assert isinstance(voices, list)
        assert len(voices) > 0

        # Check voice structure
        for voice in voices:
            assert "id" in voice
            assert "name" in voice
            assert "language" in voice
            assert "gender" in voice

    def test_get_supported_formats(self):
        """Test supported formats."""
        config = TTSConfig()
        provider = AmazonPollyProvider(config)

        formats = provider.get_supported_formats()
        assert AudioFormat.MP3 in formats
        assert AudioFormat.OGG in formats
        assert AudioFormat.WAV in formats

    def test_save_to_file_mp3(self):
        """Test saving speech to MP3 file."""
        config = TTSConfig()
        provider = AmazonPollyProvider(config)

        output_path = ARTIFACTS_DIR / "polly_test_output.mp3"
        result = provider.save_to_file("Hello from Amazon Polly.", output_path)

        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_save_to_file_ogg(self):
        """Test saving speech to OGG file."""
        config = TTSConfig()
        provider = AmazonPollyProvider(config)

        output_path = ARTIFACTS_DIR / "polly_test_output.ogg"
        result = provider.save_to_file(
            "Testing OGG format output.", output_path, format=AudioFormat.OGG
        )

        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_save_with_different_voice(self):
        """Test saving with a specific voice."""
        config = TTSConfig()
        provider = AmazonPollyProvider(config)

        output_path = ARTIFACTS_DIR / "polly_test_matthew_voice.mp3"
        result = provider.save_to_file("This is the Matthew voice.", output_path, voice="Matthew")

        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_save_with_rate_adjustment(self):
        """Test saving with rate adjustment."""
        config = TTSConfig()
        provider = AmazonPollyProvider(config)

        output_path = ARTIFACTS_DIR / "polly_test_fast_rate.mp3"
        result = provider.save_to_file("This is spoken at a faster rate.", output_path, rate=200)

        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0


class TestAmazonPollyProviderMocked:
    """Test Amazon Polly provider with mocked dependencies."""

    @patch("gensay.providers.amazon_polly.BOTO3_AVAILABLE", False)
    def test_provider_without_library(self):
        """Test provider fails when library not installed."""
        config = TTSConfig()
        with pytest.raises(ImportError, match="Please install it with"):
            AmazonPollyProvider(config)

    @patch.dict(
        os.environ, {"AWS_ACCESS_KEY_ID": "test-key", "AWS_SECRET_ACCESS_KEY": "test-secret"}
    )
    @patch("boto3.client")
    def test_wrap_with_rate(self, mock_boto_client):
        """Test SSML rate wrapping."""
        config = TTSConfig()
        provider = AmazonPollyProvider(config)

        # No rate - just wrap in speak tags
        ssml = provider._wrap_with_rate("Hello", None)
        assert ssml == "<speak>Hello</speak>"

        # Normal rate (150 WPM) = 100%
        ssml = provider._wrap_with_rate("Hello", 150)
        assert 'rate="100%"' in ssml

        # Fast rate (300 WPM) = 200%
        ssml = provider._wrap_with_rate("Hello", 300)
        assert 'rate="200%"' in ssml

        # Slow rate (75 WPM) = 50%
        ssml = provider._wrap_with_rate("Hello", 75)
        assert 'rate="50%"' in ssml

    @patch.dict(
        os.environ, {"AWS_ACCESS_KEY_ID": "test-key", "AWS_SECRET_ACCESS_KEY": "test-secret"}
    )
    @patch("boto3.client")
    def test_engine_selection(self, mock_boto_client):
        """Test engine selection from config."""
        # Default engine is neural
        config = TTSConfig()
        provider = AmazonPollyProvider(config)
        assert provider.engine == "neural"

        # Standard engine from config
        config_std = TTSConfig(extra={"engine": "standard"})
        provider_std = AmazonPollyProvider(config_std)
        assert provider_std.engine == "standard"

    @patch.dict(
        os.environ, {"AWS_ACCESS_KEY_ID": "test-key", "AWS_SECRET_ACCESS_KEY": "test-secret"}
    )
    @patch("boto3.client")
    def test_region_from_config(self, mock_boto_client):
        """Test region selection from config."""
        config = TTSConfig(extra={"aws_region": "eu-west-1"})
        AmazonPollyProvider(config)

        mock_boto_client.assert_called_once()
        call_kwargs = mock_boto_client.call_args[1]
        assert call_kwargs["region_name"] == "eu-west-1"

    @patch.dict(
        os.environ, {"AWS_ACCESS_KEY_ID": "test-key", "AWS_SECRET_ACCESS_KEY": "test-secret"}
    )
    @patch("boto3.client")
    def test_get_engine_for_voice_with_cache(self, mock_boto_client):
        """Test engine selection based on voice capabilities."""
        config = TTSConfig()
        provider = AmazonPollyProvider(config)

        # Populate voice cache with test data
        provider._voice_cache = [
            {"id": "Joanna", "supported_engines": ["neural", "standard"]},
            {"id": "Ivy", "supported_engines": ["standard"]},
        ]

        # Neural voice should return neural
        assert provider._get_engine_for_voice("Joanna") == "neural"

        # Standard-only voice should return standard
        assert provider._get_engine_for_voice("Ivy") == "standard"

        # Unknown voice should fall back to configured engine
        assert provider._get_engine_for_voice("Unknown") == "neural"
