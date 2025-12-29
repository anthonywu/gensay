"""Amazon Polly TTS provider implementation."""

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

from ..cache import TTSCache
from .base import AudioFormat, TTSConfig, TTSProvider


def _get_credentials_from_aws_cli() -> dict[str, str] | None:
    """Get credentials from AWS CLI (supports SSO, etc.)."""
    try:
        result = subprocess.run(
            ["aws", "configure", "export-credentials", "--format", "env"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            creds = {}
            for line in result.stdout.strip().split("\n"):
                if line.startswith("export "):
                    line = line[7:]  # Remove 'export '
                if "=" in line:
                    key, value = line.split("=", 1)
                    creds[key] = value
            if "AWS_ACCESS_KEY_ID" in creds and "AWS_SECRET_ACCESS_KEY" in creds:
                return creds
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


class AmazonPollyProvider(TTSProvider):
    """TTS provider using Amazon Polly service.

    AWS credentials can be provided via:
    1. Environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
    2. AWS credentials file: ~/.aws/credentials
    3. IAM role (when running on AWS infrastructure)
    4. Config extra: config.extra['aws_access_key_id'], config.extra['aws_secret_access_key']
    """

    # Map our formats to Polly output formats
    FORMAT_MAP = {
        AudioFormat.MP3: "mp3",
        AudioFormat.OGG: "ogg_vorbis",
        AudioFormat.WAV: "pcm",  # PCM is raw audio, we'll need to convert
        AudioFormat.FLAC: "mp3",  # Fallback - Polly doesn't support FLAC
        AudioFormat.AAC: "mp3",  # Fallback
        AudioFormat.M4A: "mp3",  # Fallback
    }

    # Polly engines
    ENGINE_STANDARD = "standard"
    ENGINE_NEURAL = "neural"
    ENGINE_LONG_FORM = "long-form"
    ENGINE_GENERATIVE = "generative"

    def __init__(self, config: TTSConfig | None = None):
        super().__init__(config)

        if not BOTO3_AVAILABLE:
            raise ImportError("boto3 library not found. Please install it with: pip install boto3")

        # Get credentials from config or environment
        aws_access_key = (config.extra.get("aws_access_key_id") if config else None) or os.getenv(
            "AWS_ACCESS_KEY_ID"
        )
        aws_secret_key = (
            config.extra.get("aws_secret_access_key") if config else None
        ) or os.getenv("AWS_SECRET_ACCESS_KEY")
        aws_profile = (config.extra.get("aws_profile") if config else None) or os.getenv(
            "AWS_PROFILE"
        )
        region = (
            (config.extra.get("aws_region") if config else None)
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or "us-east-1"
        )

        # Create Polly client
        # boto3 will use credentials from environment, ~/.aws/credentials, ~/.aws/config,
        # SSO, or IAM role if not explicitly provided
        if aws_access_key and aws_secret_key:
            # Explicit credentials provided
            self.client = boto3.client(
                "polly",
                region_name=region,
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
            )
        elif aws_profile:
            # Use named profile (supports SSO, assume-role, etc.)
            session = boto3.Session(profile_name=aws_profile, region_name=region)
            self.client = session.client("polly")
        else:
            # Try boto3 default credential chain first
            self.client = boto3.client("polly", region_name=region)
            # Verify credentials work, fall back to AWS CLI if needed
            try:
                boto3.client("sts", region_name=region).get_caller_identity()
            except NoCredentialsError:
                # Fallback: get credentials from AWS CLI (supports SSO login cache)
                if cli_creds := _get_credentials_from_aws_cli():
                    self.client = boto3.client(
                        "polly",
                        region_name=cli_creds.get("AWS_DEFAULT_REGION", region),
                        aws_access_key_id=cli_creds["AWS_ACCESS_KEY_ID"],
                        aws_secret_access_key=cli_creds["AWS_SECRET_ACCESS_KEY"],
                        aws_session_token=cli_creds.get("AWS_SESSION_TOKEN"),
                    )

        # Default engine - neural voices sound better but cost more
        self.engine = (config.extra.get("engine") if config else None) or self.ENGINE_NEURAL

        # Cache for voice list
        self._voice_cache: list[dict[str, Any]] | None = None
        self._cache = TTSCache(enabled=config.cache_enabled if config else True)

    def speak(self, text: str, voice: str | None = None, rate: int | None = None) -> None:
        """Speak text using Amazon Polly."""
        voice = voice or self.config.voice or "Joanna"  # Default US English neural voice

        try:
            self.update_progress(0.0, "Checking cache...")

            ssml_text = self._wrap_with_rate(text, rate)
            engine = self._get_engine_for_voice(voice)
            cache_key = self._get_cache_key(ssml_text, voice, engine, "mp3")

            audio_data = self._cache.get(cache_key)

            if audio_data is None:
                self.update_progress(0.2, "Generating speech...")

                # Generate audio to a temp file, then play it
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    temp_path = Path(f.name)

                # Synthesize speech
                response = self.client.synthesize_speech(
                    Text=ssml_text,
                    TextType="ssml",
                    OutputFormat="mp3",
                    VoiceId=voice,
                    Engine=engine,
                )

                self.update_progress(0.5, "Playing audio...")

                # Write audio stream to file and cache
                audio_data = response["AudioStream"].read()
                temp_path.write_bytes(audio_data)
                self._cache.put(cache_key, audio_data)

                # Play using afplay on macOS
                subprocess.run(["afplay", str(temp_path)], check=True)
            else:
                self.update_progress(0.5, "Using cached audio...")

                # Write to temp file for playback
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    temp_path = Path(f.name)
                temp_path.write_bytes(audio_data)

                # Play using afplay on macOS
                subprocess.run(["afplay", str(temp_path)], check=True)

            self.update_progress(1.0, "Complete")

        except (BotoCoreError, ClientError) as e:
            raise RuntimeError(f"Amazon Polly TTS failed: {e}") from e
        finally:
            # Clean up temp file
            if temp_path.exists():
                temp_path.unlink()

    def save_to_file(
        self,
        text: str,
        output_path: str | Path,
        voice: str | None = None,
        rate: int | None = None,
        format: AudioFormat | None = None,
    ) -> Path:
        """Save speech to file using Amazon Polly."""
        output_path = Path(output_path)
        voice = voice or self.config.voice or "Joanna"
        format = format or self.config.format or AudioFormat.from_extension(output_path)

        # Map format to Polly format
        polly_format = self.FORMAT_MAP.get(format, "mp3")
        ssml_text = self._wrap_with_rate(text, rate)
        engine = self._get_engine_for_voice(voice)
        cache_key = self._get_cache_key(ssml_text, voice, engine, polly_format)

        try:
            self.update_progress(0.0, "Checking cache...")

            audio_data = self._cache.get(cache_key)

            if audio_data is None:
                self.update_progress(0.2, "Generating speech...")

                response = self.client.synthesize_speech(
                    Text=ssml_text,
                    TextType="ssml",
                    OutputFormat=polly_format,
                    VoiceId=voice,
                    Engine=engine,
                )

                self.update_progress(0.5, "Saving to file...")

                # Write audio stream to file and cache
                audio_data = response["AudioStream"].read()
                output_path.write_bytes(audio_data)
                self._cache.put(cache_key, audio_data)
            else:
                self.update_progress(0.5, "Using cached audio...")
                output_path.write_bytes(audio_data)

            self.update_progress(1.0, "Complete")

            return output_path

        except (BotoCoreError, ClientError) as e:
            raise RuntimeError(f"Amazon Polly TTS failed: {e}") from e

    def list_voices(self) -> list[dict[str, Any]]:
        """List available Amazon Polly voices."""
        if self._voice_cache is None:
            try:
                # Get all available voices
                response = self.client.describe_voices()
                self._voice_cache = []

                for voice in response.get("Voices", []):
                    voice_data = {
                        "id": voice["Id"],
                        "name": voice["Name"],
                        "language": voice["LanguageCode"],
                        "language_name": voice["LanguageName"],
                        "gender": voice["Gender"],
                        "supported_engines": voice.get("SupportedEngines", ["standard"]),
                    }
                    self._voice_cache.append(voice_data)

                # Paginate if needed
                while "NextToken" in response:
                    response = self.client.describe_voices(NextToken=response["NextToken"])
                    for voice in response.get("Voices", []):
                        voice_data = {
                            "id": voice["Id"],
                            "name": voice["Name"],
                            "language": voice["LanguageCode"],
                            "language_name": voice["LanguageName"],
                            "gender": voice["Gender"],
                            "supported_engines": voice.get("SupportedEngines", ["standard"]),
                        }
                        self._voice_cache.append(voice_data)

            except (BotoCoreError, ClientError) as e:
                raise RuntimeError(f"Failed to list voices: {e}") from e

        return self._voice_cache

    def get_supported_formats(self) -> list[AudioFormat]:
        """Get supported audio formats.

        Amazon Polly natively supports: mp3, ogg_vorbis, pcm
        Other formats use mp3 as fallback.
        """
        return [
            AudioFormat.MP3,
            AudioFormat.OGG,
            AudioFormat.WAV,  # via pcm
            # These use mp3 as fallback
            AudioFormat.FLAC,
            AudioFormat.AAC,
            AudioFormat.M4A,
        ]

    def _wrap_with_rate(self, text: str, rate: int | None) -> str:
        """Wrap text in SSML with prosody rate if specified.

        Polly accepts rate as percentage: "50%" (slow) to "200%" (fast).
        Normal speaking rate is ~150 WPM.
        """
        if rate is None:
            rate = self.config.rate

        if rate is None:
            # No rate adjustment, just wrap in speak tags
            return f"<speak>{text}</speak>"

        # Convert WPM to percentage (150 WPM = 100%)
        rate_percent = int((rate / 150.0) * 100)
        # Clamp to Polly's supported range
        rate_percent = max(20, min(200, rate_percent))

        return f'<speak><prosody rate="{rate_percent}%">{text}</prosody></speak>'

    def _get_engine_for_voice(self, voice_id: str) -> str:
        """Get appropriate engine for a voice.

        Neural voices require 'neural' engine, standard voices use 'standard'.
        Falls back to configured engine or 'neural'.
        """
        # If we have cached voice info, check what engines voice supports
        if self._voice_cache:
            for voice in self._voice_cache:
                if voice["id"] == voice_id:
                    supported = voice.get("supported_engines", [])
                    # Prefer neural if available, then standard
                    if "neural" in supported:
                        return "neural"
                    if "standard" in supported:
                        return "standard"
                    if supported:
                        return supported[0]

        # Fall back to configured engine
        return self.engine

    def _get_cache_key(self, ssml_text: str, voice: str, engine: str, format: str) -> str:
        """Generate cache key for SSML text/voice/engine/format combination."""
        data = f"polly|{ssml_text}|{voice}|{engine}|{format}"
        return hashlib.sha256(data.encode()).hexdigest()
