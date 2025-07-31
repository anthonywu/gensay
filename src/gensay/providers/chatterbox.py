"""Chatterbox TTS provider implementation."""

import hashlib
import os
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

# Set attention implementation to eager before importing torch/transformers
os.environ["ATTN_IMPLEMENTATION"] = "eager"

from tqdm import tqdm

from ..cache import TTSCache
from ..text_chunker import ChunkingConfig, TextChunker
from .base import AudioFormat, TTSConfig, TTSProvider


class ChatterboxProvider(TTSProvider):
    """TTS provider using Chatterbox library."""

    def __init__(self, config: TTSConfig | None = None):
        super().__init__(config)
        self._cache = TTSCache(enabled=config.cache_enabled if config else True)

        # Create ChunkingConfig with max_chunk_size
        chunking_config = ChunkingConfig(
            max_chunk_size=config.extra.get("chunk_size", 500) if config else 500
        )
        self._chunker = TextChunker(chunking_config)

        self._cache_queue = queue.Queue()
        self._cache_thread = None
        self._stop_caching = threading.Event()
        self._cache_thread_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._pyaudio = None
        self._pyaudio_lock = threading.Lock()

        # Initialize Chatterbox
        try:
            # Ensure attention is set to eager mode
            os.environ["ATTN_IMPLEMENTATION"] = "eager"
            os.environ["TRANSFORMERS_ATTN_IMPLEMENTATION"] = "eager"

            import chatterbox

            self._chatterbox = chatterbox
            # Initialize ChatterboxTTS with default pretrained model
            device = config.extra.get("device", "cpu") if config else "cpu"
            self._tts = chatterbox.ChatterboxTTS.from_pretrained(device)
        except ImportError as e:
            raise ImportError("Chatterbox library not found. Please install it first.") from e

    def speak(self, text: str, voice: str | None = None, rate: int | None = None) -> None:
        """Speak text using Chatterbox."""
        voice = voice or self.config.voice or "default"
        rate = rate or self.config.rate or 150

        chunks = self._chunker.chunk_text(text)
        total_chunks = len(chunks)

        # Use tqdm for progress by default
        progress_bar = None
        if self.config.extra.get("show_progress", True):
            progress_bar = tqdm(total=total_chunks, desc="Speaking", unit="chunk")

        try:
            for i, chunk in enumerate(chunks):
                # Update progress
                progress = (i + 1) / total_chunks
                self.update_progress(progress, f"Speaking chunk {i + 1}/{total_chunks}")

                # Check cache first
                cache_key = self._get_cache_key(chunk, voice, rate)
                audio_data = self._cache.get(cache_key)

                if audio_data is None:
                    # Generate audio
                    audio_data = self._generate_audio(chunk, voice, rate)
                    self._cache.put(cache_key, audio_data)

                # Play audio
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

        # Progress tracking
        progress_bar = None
        if self.config.extra.get("show_progress", True):
            progress_bar = tqdm(total=len(chunks), desc="Generating", unit="chunk")

        try:
            for i, chunk in enumerate(chunks):
                progress = (i + 1) / len(chunks)
                self.update_progress(progress, f"Processing chunk {i + 1}/{len(chunks)}")

                # Check cache
                cache_key = self._get_cache_key(chunk, voice, rate)
                audio_data = self._cache.get(cache_key)

                if audio_data is None:
                    audio_data = self._generate_audio(chunk, voice, rate)
                    self._cache.put(cache_key, audio_data)

                audio_segments.append(audio_data)

                if progress_bar:
                    progress_bar.update(1)
        finally:
            if progress_bar:
                progress_bar.close()

        # Combine audio segments and save
        combined_audio = self._combine_audio_segments(audio_segments)
        self._save_audio(combined_audio, output_path, format)

        return output_path

    def list_voices(self) -> list[dict[str, Any]]:
        """List available Chatterbox voices."""
        # Chatterbox uses audio prompts for voice cloning rather than preset voices
        voices = [
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
        return voices

    def get_supported_formats(self) -> list[AudioFormat]:
        """Get supported audio formats."""
        # Chatterbox typically supports these formats
        return [AudioFormat.WAV, AudioFormat.M4A, AudioFormat.MP3]

    def cache_ahead(self, text: str, voice: str | None = None, rate: int | None = None) -> None:
        """Queue text for background caching."""
        voice = voice or self.config.voice or "default"
        rate = rate or self.config.rate or 150

        chunks = self._chunker.chunk_text(text)
        for chunk in chunks:
            self._cache_queue.put((chunk, voice, rate))

        # Start background caching thread if not running
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

                # Skip if already cached
                if self._cache.get(cache_key) is None:
                    audio_data = self._generate_audio(chunk, voice, rate)
                    self._cache.put(cache_key, audio_data)

                self._cache_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Cache worker error: {e}")

    def _get_cache_key(self, text: str, voice: str, rate: int) -> str:
        """Generate cache key for text/voice/rate combination."""
        data = f"{text}|{voice}|{rate}"
        return hashlib.sha256(data.encode()).hexdigest()

    def _generate_audio(self, text: str, voice: str, rate: int) -> bytes:
        """Generate audio data using Chatterbox."""
        try:
            # Generate audio using ChatterboxTTS
            # Note: rate parameter might need to be mapped to temperature or other params
            audio_prompt_path = None
            if voice != "default" and Path(voice).exists():
                audio_prompt_path = voice

            wav_array = self._tts.generate(
                text=text,
                audio_prompt_path=audio_prompt_path,
                temperature=0.8,  # Could map rate to temperature
                repetition_penalty=1.2,
            )

            # Convert torch tensor to bytes (assuming 16-bit PCM at 24kHz)
            import numpy as np

            # Convert tensor to numpy array first
            if hasattr(wav_array, "cpu"):  # It's a torch tensor
                wav_numpy = wav_array.cpu().numpy()
            else:
                wav_numpy = wav_array

            # Ensure we have a 1D array
            if wav_numpy.ndim > 1:
                # If stereo, convert to mono by averaging channels
                if wav_numpy.shape[0] == 2 or (wav_numpy.ndim == 2 and wav_numpy.shape[1] == 2):
                    wav_numpy = wav_numpy.mean(axis=-1)
                else:
                    # Flatten if needed
                    wav_numpy = wav_numpy.flatten()

            # Validate audio range
            if wav_numpy.max() > 1.0 or wav_numpy.min() < -1.0:
                # Normalize if out of range
                max_val = max(abs(wav_numpy.max()), abs(wav_numpy.min()))
                if max_val > 0:
                    wav_numpy = wav_numpy / max_val

            # Convert to 16-bit PCM
            wav_int16 = (wav_numpy * 32767).astype(np.int16)
            return wav_int16.tobytes()
        except Exception as e:
            raise RuntimeError(f"Failed to generate audio: {e}") from e

    def _play_audio(self, audio_data: bytes) -> None:
        """Play audio data."""
        try:
            import pyaudio

            with self._pyaudio_lock:
                # Initialize PyAudio once
                if self._pyaudio is None:
                    self._pyaudio = pyaudio.PyAudio()

            # Chatterbox generates 24kHz audio
            stream = self._pyaudio.open(format=pyaudio.paInt16, channels=1, rate=24000, output=True)

            try:
                # Play the audio
                stream.write(audio_data)
            finally:
                # Always close the stream
                stream.stop_stream()
                stream.close()
        except Exception as e:
            raise RuntimeError(f"Failed to play audio: {e}") from e

    def _combine_audio_segments(self, segments: list[bytes]) -> bytes:
        """Combine multiple audio segments."""
        # Simple concatenation for raw PCM audio
        return b"".join(segments)

    def _save_audio(self, audio_data: bytes, path: Path, format: AudioFormat) -> None:
        """Save audio data to file."""
        try:
            import wave

            if format == AudioFormat.WAV:
                # Save as WAV file
                with wave.open(str(path), "wb") as wf:
                    wf.setnchannels(1)  # Mono
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(24000)  # 24kHz
                    wf.writeframes(audio_data)
            elif format in (AudioFormat.MP3, AudioFormat.M4A):
                # For MP3/M4A, we need to convert through WAV first
                try:
                    import io

                    from pydub import AudioSegment

                    # Create WAV in memory
                    wav_buffer = io.BytesIO()
                    with wave.open(wav_buffer, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(24000)
                        wf.writeframes(audio_data)

                    # Convert to desired format
                    wav_buffer.seek(0)
                    audio = AudioSegment.from_wav(wav_buffer)

                    if format == AudioFormat.MP3:
                        audio.export(str(path), format="mp3", bitrate="192k")
                    else:  # M4A
                        audio.export(str(path), format="mp4", codec="aac", bitrate="192k")
                except ImportError:
                    # Fallback: save as WAV with warning
                    wav_path = path.with_suffix(".wav")
                    with wave.open(str(wav_path), "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(24000)
                        wf.writeframes(audio_data)
                    raise RuntimeError(
                        f"Format {format} requires pydub. Install with: pip install pydub. "
                        f"Audio saved as WAV to {wav_path}"
                    )
            else:
                raise ValueError(f"Unsupported audio format: {format}")
        except Exception as e:
            raise RuntimeError(f"Failed to save audio: {e}") from e

    def __del__(self):
        """Cleanup resources."""
        if hasattr(self, "_stop_caching"):
            self.stop_cache_ahead()
        if hasattr(self, "_executor"):
            self._executor.shutdown(wait=False)
        if hasattr(self, "_pyaudio") and self._pyaudio is not None:
            try:
                self._pyaudio.terminate()
            except Exception:
                pass  # Ignore errors during cleanup
