"""Chatterbox TTS provider implementation using ChatterboxTurboTTS."""

import hashlib
import io
import os
import platform
import queue
import shutil
import subprocess
import threading
import wave
from pathlib import Path
from typing import Any

from tqdm import tqdm

from ..cache import TTSCache
from ..text_chunker import ChunkingConfig, TextChunker
from .base import AudioFormat, TTSConfig, TTSProvider


def _find_ffmpeg_lib_path() -> str | None:
    """Find FFmpeg library path on the system.

    Returns the path to FFmpeg's lib directory, or None if not found.
    """
    if platform.system() != "Darwin":
        return None

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        return None

    # Try Nix-specific detection first (split outputs: bin and lib are separate)
    try:
        result = subprocess.run(
            ["nix-store", "-qR", ffmpeg_path],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if "ffmpeg" in line and line.endswith("-lib"):
                    lib_path = f"{line}/lib"
                    if Path(lib_path).exists():
                        return lib_path
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback: check relative to ffmpeg binary (Homebrew-style)
    ffmpeg_real = Path(ffmpeg_path).resolve()
    lib_dir = ffmpeg_real.parent.parent / "lib"
    if lib_dir.exists() and any(lib_dir.glob("libav*.dylib")):
        return str(lib_dir)

    return None


class FFmpegLibraryError(RuntimeError):
    """Raised when FFmpeg libraries are not properly configured."""

    pass


def _check_ffmpeg_libs() -> None:
    """Check that FFmpeg libs are available for TorchCodec.

    On macOS, DYLD_LIBRARY_PATH must be set before the process starts.
    If not set, detect the path and tell the user how to fix it.
    """
    if platform.system() != "Darwin":
        return

    lib_path = _find_ffmpeg_lib_path()
    if not lib_path:
        return  # No FFmpeg found, let torchcodec handle the error

    current = os.environ.get("DYLD_LIBRARY_PATH", "")
    if lib_path in current.split(":"):
        return  # Already set correctly

    raise FFmpegLibraryError(
        f"FFmpeg libraries not in DYLD_LIBRARY_PATH.\n"
        f"TorchCodec requires FFmpeg libs to be available at process start.\n\n"
        f"Run this before starting gensay, or persist in your shell profile:\n\n"
        f'  export DYLD_LIBRARY_PATH="{lib_path}:$DYLD_LIBRARY_PATH"'
    )


class ChatterboxProvider(TTSProvider):
    """TTS provider using ChatterboxTurboTTS."""

    def __init__(self, config: TTSConfig | None = None):
        super().__init__(config)
        self._cache = TTSCache(enabled=config.cache_enabled if config else True)

        chunking_config = ChunkingConfig(
            max_chunk_size=config.extra.get("chunk_size", 500) if config else 500
        )
        self._chunker = TextChunker(chunking_config)

        self._cache_queue: queue.Queue = queue.Queue()
        self._cache_thread: threading.Thread | None = None
        self._stop_caching = threading.Event()
        self._cache_thread_lock = threading.Lock()

        self._ta: Any = None
        self._tts: Any = None
        self._device: str = "mps" if platform.system() == "Darwin" else "cuda"
        self._model_loaded = False

    def _load_model(self) -> None:
        """Load ChatterboxTurboTTS model (lazy loading)."""
        if self._model_loaded:
            return

        # Check FFmpeg libs before importing torchaudio
        _check_ffmpeg_libs()

        try:
            import torchaudio as ta
            from chatterbox.tts_turbo import ChatterboxTurboTTS

            self._ta = ta
            device = self.config.extra.get("device", self._device) if self.config else self._device
            self._tts = ChatterboxTurboTTS.from_pretrained(device=device)
            self._device = device
            self._model_loaded = True
        except ImportError as e:
            raise ImportError(
                "Chatterbox dependencies not found. Install with: "
                "uv tool install 'gensay[chatterbox]' "
                "--with git+https://github.com/anthonywu/chatterbox.git@allow-dep-updates"
            ) from e

    @property
    def sample_rate(self) -> int:
        """Get the model's sample rate."""
        self._load_model()
        return self._tts.sr

    def speak(self, text: str, voice: str | None = None, rate: int | None = None) -> None:
        """Speak text using Chatterbox."""
        voice = voice or self.config.voice or "default"
        rate = rate or self.config.rate or 150

        chunks = self._chunker.chunk_text(text)
        total_chunks = len(chunks)

        progress_bar = None
        if self.config.extra.get("show_progress", True):
            progress_bar = tqdm(total=total_chunks, desc="Speaking", unit="chunk")

        try:
            for i, chunk in enumerate(chunks):
                progress = (i + 1) / total_chunks
                self.update_progress(progress, f"Speaking chunk {i + 1}/{total_chunks}")

                cache_key = self._get_cache_key(chunk, voice, rate)
                audio_data = self._cache.get(cache_key)

                if audio_data is None:
                    audio_data = self._generate_audio(chunk, voice)
                    self._cache.put(cache_key, audio_data)

                self._play_audio(audio_data)

                if progress_bar:
                    progress_bar.update(1)
        finally:
            if progress_bar:
                progress_bar.close()

    def save_to_file(
        self,
        text: str,
        output_path: str | Path,
        voice: str | None = None,
        rate: int | None = None,
        format: AudioFormat | None = None,
    ) -> Path:
        """Save speech to file."""
        output_path = Path(output_path)
        voice = voice or self.config.voice or "default"
        rate = rate or self.config.rate or 150
        format = format or self.config.format or AudioFormat.from_extension(output_path)

        if not self.is_format_supported(format):
            raise ValueError(f"Format {format} not supported by Chatterbox")

        chunks = self._chunker.chunk_text(text)
        audio_segments = []

        progress_bar = None
        if self.config.extra.get("show_progress", True):
            progress_bar = tqdm(total=len(chunks), desc="Generating", unit="chunk")

        try:
            for i, chunk in enumerate(chunks):
                progress = (i + 1) / len(chunks)
                self.update_progress(progress, f"Processing chunk {i + 1}/{len(chunks)}")

                cache_key = self._get_cache_key(chunk, voice, rate)
                audio_data = self._cache.get(cache_key)

                if audio_data is None:
                    audio_data = self._generate_audio(chunk, voice)
                    self._cache.put(cache_key, audio_data)

                audio_segments.append(audio_data)

                if progress_bar:
                    progress_bar.update(1)
        finally:
            if progress_bar:
                progress_bar.close()

        combined_audio = self._combine_audio_segments(audio_segments)
        self._save_audio(combined_audio, output_path, format)

        return output_path

    def list_voices(self) -> list[dict[str, Any]]:
        """List available Chatterbox voices."""
        return [
            {
                "id": "default",
                "name": "Default Voice",
                "language": "en-US",
                "gender": "neutral",
                "description": "Default Chatterbox voice",
            },
            {
                "id": "custom",
                "name": "Custom Voice (provide audio file path)",
                "language": "en-US",
                "gender": "neutral",
                "description": "Use an audio file path as voice parameter for voice cloning",
            },
        ]

    def get_supported_formats(self) -> list[AudioFormat]:
        """Get supported audio formats."""
        return [AudioFormat.WAV, AudioFormat.M4A, AudioFormat.MP3]

    def cache_ahead(self, text: str, voice: str | None = None, rate: int | None = None) -> None:
        """Queue text for background caching."""
        voice = voice or self.config.voice or "default"
        rate = rate or self.config.rate or 150

        chunks = self._chunker.chunk_text(text)
        for chunk in chunks:
            self._cache_queue.put((chunk, voice, rate))

        with self._cache_thread_lock:
            if self._cache_thread is None or not self._cache_thread.is_alive():
                self._stop_caching.clear()
                self._cache_thread = threading.Thread(target=self._cache_worker)
                self._cache_thread.daemon = True
                self._cache_thread.start()

    def stop_cache_ahead(self) -> None:
        """Stop background caching."""
        self._stop_caching.set()
        with self._cache_thread_lock:
            if self._cache_thread:
                self._cache_thread.join(timeout=1.0)

    def _cache_worker(self) -> None:
        """Background worker for cache-ahead functionality."""
        while not self._stop_caching.is_set():
            try:
                chunk, voice, rate = self._cache_queue.get(timeout=0.5)
                cache_key = self._get_cache_key(chunk, voice, rate)

                if self._cache.get(cache_key) is None:
                    audio_data = self._generate_audio(chunk, voice)
                    self._cache.put(cache_key, audio_data)

                self._cache_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Cache worker error: {e}")

    def _get_cache_key(self, text: str, voice: str, rate: int) -> str:
        """Generate cache key for text/voice/rate combination."""
        data = f"turbo|{text}|{voice}|{rate}"
        return hashlib.sha256(data.encode()).hexdigest()

    def _generate_audio(self, text: str, voice: str) -> bytes:
        """Generate audio data using ChatterboxTurboTTS."""
        self._load_model()
        generate_kwargs: dict[str, Any] = {}
        if voice != "default" and Path(voice).exists():
            generate_kwargs["audio_prompt_path"] = voice

        wav = self._tts.generate(text, **generate_kwargs)

        if wav is None:
            raise RuntimeError(f"ChatterboxTurboTTS.generate returned None for text: {text!r}")

        # Convert tensor to WAV bytes for caching/playback
        # TorchCodec backend can't write to BytesIO (needs file extension),
        # so we use a temp file
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name
        try:
            self._ta.save(temp_path, wav, self.sample_rate)
            return Path(temp_path).read_bytes()
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def _play_audio(self, audio_data: bytes) -> None:
        """Play audio data using system audio player."""
        import tempfile

        # Write to temp file and play with system player
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_data)
            temp_path = f.name

        try:
            players = ["afplay", "ffplay", "aplay", "paplay"]
            for player in players:
                if shutil.which(player):
                    cmd = [player]
                    if player == "ffplay":
                        cmd.extend(["-nodisp", "-autoexit"])
                    cmd.append(temp_path)
                    subprocess.run(cmd, check=True)
                    break
            else:
                raise RuntimeError("No audio player found (tried: afplay, ffplay, aplay, paplay)")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def _combine_audio_segments(self, segments: list[bytes]) -> bytes:
        """Combine multiple WAV audio segments."""
        if not segments:
            return b""

        if len(segments) == 1:
            return segments[0]

        # Read all WAV segments and concatenate the audio data
        combined_frames = b""
        params = None

        for segment in segments:
            with wave.open(io.BytesIO(segment), "rb") as wf:
                if params is None:
                    params = wf.getparams()
                combined_frames += wf.readframes(wf.getnframes())

        if params is None:
            return b""

        # Write combined WAV
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            wf.setparams(params)
            wf.writeframes(combined_frames)

        return buffer.getvalue()

    def _save_audio(self, audio_data: bytes, path: Path, format: AudioFormat) -> None:
        """Save audio data to file."""
        if format == AudioFormat.WAV:
            path.write_bytes(audio_data)
        elif format in (AudioFormat.MP3, AudioFormat.M4A):
            try:
                from pydub import AudioSegment

                audio = AudioSegment.from_wav(io.BytesIO(audio_data))
                if format == AudioFormat.MP3:
                    audio.export(str(path), format="mp3", bitrate="192k")
                else:
                    audio.export(str(path), format="mp4", codec="aac", bitrate="192k")
            except ImportError:
                wav_path = path.with_suffix(".wav")
                wav_path.write_bytes(audio_data)
                raise RuntimeError(
                    f"Format {format} requires pydub. Install with: pip install pydub. "
                    f"Audio saved as WAV to {wav_path}"
                ) from None
        else:
            raise ValueError(f"Unsupported audio format: {format}")

    def __del__(self):
        """Cleanup resources."""
        if hasattr(self, "_stop_caching"):
            self.stop_cache_ahead()
