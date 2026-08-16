"""VibeVoice-Realtime TTS provider using MLX (Apple Silicon local inference).

Runs Microsoft's VibeVoice-Realtime model via the ``mlx-audio`` library.
Voices ship embedded in the model repo (``voices/*.safetensors``); pass a
voice name like ``en-Emma_woman``.
"""

import hashlib
import io
import platform
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from tqdm import tqdm

from ..cache import TTSCache
from ..text_chunker import ChunkingConfig, TextChunker
from .base import AudioFormat, TTSConfig, TTSProvider
from .playback import play_audio_bytes

DEFAULT_MODEL_REPO_ID = "mlx-community/VibeVoice-Realtime-0.5B-fp16"
MODEL_DOWNLOAD_SIZE_HINT = "~2.2 GB"
DEFAULT_VOICE = "en-Emma_woman"

# Voice names bundled with the mlx-community VibeVoice-Realtime repos
# (voices/*.safetensors). Used as a fallback when the local snapshot is not
# available to enumerate; the model itself is single-speaker per generation.
KNOWN_VOICES: tuple[str, ...] = (
    "en-Carter_man",
    "en-Davis_man",
    "en-Emma_woman",
    "en-Frank_man",
    "en-Grace_woman",
    "en-Mike_man",
    "de-Spk0_man",
    "de-Spk1_woman",
    "fr-Spk0_man",
    "fr-Spk1_woman",
    "in-Samuel_man",
    "it-Spk0_woman",
    "it-Spk1_man",
    "jp-Spk0_man",
    "jp-Spk1_woman",
    "kr-Spk0_woman",
    "kr-Spk1_man",
    "nl-Spk0_man",
    "nl-Spk1_woman",
    "pl-Spk0_man",
    "pl-Spk1_woman",
    "pt-Spk0_woman",
    "pt-Spk1_man",
    "sp-Spk0_woman",
    "sp-Spk1_man",
)


class ModelDownloadDeclinedError(RuntimeError):
    """User declined the initial model download."""


def _model_cached(repo_id: str) -> bool:
    """True if the model snapshot is already in the local HuggingFace cache."""
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(repo_id, local_files_only=True)
        return True
    except Exception:
        return False  # cache miss (or offline)


def _confirm_model_download(repo_id: str) -> None:
    """Inform + confirm before the first model download; default answer is Yes.

    Non-interactive callers (daemon, pipes) proceed with an stderr note —
    explicitly choosing vibevoice already implies consent.
    """
    if _model_cached(repo_id):
        return
    msg = (
        f"vibevoice: model '{repo_id}' not in the local HuggingFace cache; "
        f"first use downloads {MODEL_DOWNLOAD_SIZE_HINT}. "
    )
    if sys.stdin.isatty():
        ans = input(msg + "Download now? [Y/n] ").strip().lower()
        if ans and ans not in ("y", "yes"):
            raise ModelDownloadDeclinedError(
                "vibevoice model download declined by user; nothing was downloaded"
            )
    else:
        print(msg + "Proceeding (non-interactive).", file=sys.stderr)


class VibeVoiceProvider(TTSProvider):
    """TTS provider using VibeVoice-Realtime on MLX (Apple Silicon only)."""

    def __init__(self, config: TTSConfig | None = None):
        super().__init__(config)
        self._cache = TTSCache(enabled=config.cache_enabled if config else True)

        chunking_config = ChunkingConfig(
            max_chunk_size=config.extra.get("chunk_size", 500) if config else 500
        )
        self._chunker = TextChunker(chunking_config)

        extra = config.extra if config else {}
        self._model_repo_id: str = extra.get("model") or DEFAULT_MODEL_REPO_ID
        self._model: Any = None
        # MLX (>=0.31.2) streams are thread-local: a model loaded on one
        # thread cannot generate on another (e.g. daemon warmup vs. worker
        # threads). Pin all MLX work to one dedicated thread.
        self._mlx_thread: ThreadPoolExecutor | None = None

    @property
    def model_repo_id(self) -> str:
        return self._model_repo_id

    def warmup(self) -> None:
        """Eagerly load the VibeVoice model into memory."""
        self._on_mlx_thread(self._load_model)

    def unload(self) -> None:
        """Drop the model to free memory. Next speak reloads."""
        self._model = None

    def _on_mlx_thread(self, fn, *args):
        """Run fn on the provider's dedicated MLX thread (creating it lazily)."""
        if self._mlx_thread is None:
            self._mlx_thread = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vibevoice-mlx")
        return self._mlx_thread.submit(fn, *args).result()

    def _load_model(self) -> None:
        """Load the VibeVoice model via mlx-audio (lazy loading)."""
        if self._model is not None:
            return

        if platform.system() != "Darwin" or platform.machine() != "arm64":
            raise RuntimeError(
                "vibevoice requires Apple Silicon (MLX). Use another provider on this platform."
            )

        try:
            from mlx_audio.tts.utils import load_model
        except ImportError as e:
            raise ImportError(
                "VibeVoice dependencies not found. Install with: "
                "uv tool install 'gensay[vibevoice]'"
            ) from e

        _confirm_model_download(self._model_repo_id)
        self._model = load_model(self._model_repo_id)

    def _default_voice(self) -> str:
        return self.config.voice or self.config.extra.get("voice") or DEFAULT_VOICE

    def speak(self, text: str, voice: str | None = None, rate: int | None = None) -> None:
        """Speak text using VibeVoice."""
        voice = voice or self._default_voice()
        rate = rate or self.config.rate or 150

        chunks = self._chunker.chunk_text(text)
        total_chunks = len(chunks)

        progress_bar = None
        if self.config.extra.get("show_progress", True):
            progress_bar = tqdm(total=total_chunks, desc="Speaking", unit="chunk")

        try:
            for i, chunk in enumerate(chunks):
                self.update_progress(
                    (i + 1) / total_chunks, f"Speaking chunk {i + 1}/{total_chunks}"
                )
                play_audio_bytes(self._get_or_generate(chunk, voice, rate), suffix=".wav")
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
        voice = voice or self._default_voice()
        rate = rate or self.config.rate or 150
        format = format or self.config.format or AudioFormat.from_extension(output_path)

        if not self.is_format_supported(format):
            raise ValueError(f"Format {format} not supported by VibeVoice")

        chunks = self._chunker.chunk_text(text)
        audio_segments = []

        progress_bar = None
        if self.config.extra.get("show_progress", True):
            progress_bar = tqdm(total=len(chunks), desc="Generating", unit="chunk")

        try:
            for i, chunk in enumerate(chunks):
                self.update_progress(
                    (i + 1) / len(chunks), f"Processing chunk {i + 1}/{len(chunks)}"
                )
                audio_segments.append(self._get_or_generate(chunk, voice, rate))
                if progress_bar:
                    progress_bar.update(1)
        finally:
            if progress_bar:
                progress_bar.close()

        combined_audio = self._combine_audio_segments(audio_segments)
        self._save_audio(combined_audio, output_path, format)

        return output_path

    def list_voices(self) -> list[dict[str, Any]]:
        """List VibeVoice voices (from the local snapshot when available)."""
        names = self._snapshot_voice_names() or list(KNOWN_VOICES)
        voices = []
        for name in sorted(names):
            lang, _, speaker = name.partition("-")
            gender = "female" if name.endswith("_woman") else "male"
            voices.append(
                {
                    "id": name,
                    "name": speaker.replace("_", " ") or name,
                    "language": lang,
                    "gender": gender,
                    "description": f"VibeVoice embedded voice ({name})",
                }
            )
        return voices

    def list_models(self) -> list[dict[str, Any]]:
        """List the known mlx-community VibeVoice-Realtime variants."""
        variants = ("4bit", "5bit", "6bit", "8bit", "fp16")
        return [
            {
                "id": (repo := f"mlx-community/VibeVoice-Realtime-0.5B-{v}"),
                "description": f"VibeVoice-Realtime 0.5B ({v})",
                "current": repo == self._model_repo_id,
                "capabilities": ["streaming", "long-form"],
            }
            for v in variants
        ]

    def get_supported_formats(self) -> list[AudioFormat]:
        """Get supported audio formats."""
        return [AudioFormat.WAV, AudioFormat.M4A, AudioFormat.MP3]

    def _snapshot_voice_names(self) -> list[str]:
        """Voice names from the locally cached model snapshot, if present."""
        try:
            from huggingface_hub import snapshot_download

            snapshot = Path(snapshot_download(self._model_repo_id, local_files_only=True))
            return [p.stem for p in (snapshot / "voices").glob("*.safetensors")]
        except Exception:
            return []

    def _get_or_generate(self, chunk: str, voice: str, rate: int) -> bytes:
        """Return cached WAV bytes for a chunk, generating on miss."""
        cache_key = self._get_cache_key(chunk, voice, rate)
        audio_data = self._cache.get(cache_key)
        if audio_data is None:
            audio_data = self._generate_audio(chunk, voice)
            self._cache.put(cache_key, audio_data)
        return audio_data

    def _get_cache_key(self, text: str, voice: str, rate: int) -> str:
        """Generate cache key for model/text/voice/rate combination."""
        data = f"{self._model_repo_id}|{text}|{voice}|{rate}"
        return hashlib.sha256(data.encode()).hexdigest()

    def _generate_audio(self, text: str, voice: str) -> bytes:
        """Generate WAV bytes using VibeVoice (on the dedicated MLX thread)."""
        return self._on_mlx_thread(self._generate_audio_on_thread, text, voice)

    def _generate_audio_on_thread(self, text: str, voice: str) -> bytes:
        """Generate WAV bytes using VibeVoice via mlx-audio."""
        self._load_model()

        import numpy as np
        from mlx_audio.audio_io import write as audio_write

        segments = list(self._model.generate(text=text, voice=voice, verbose=False))
        if not segments:
            raise RuntimeError(f"VibeVoice returned no audio for text: {text!r}")

        audio = np.concatenate([np.asarray(seg.audio) for seg in segments])
        buffer = io.BytesIO()
        audio_write(buffer, audio, segments[0].sample_rate, format="wav")
        return buffer.getvalue()

    def _combine_audio_segments(self, segments: list[bytes]) -> bytes:
        """Combine multiple WAV audio segments."""
        import wave

        if not segments:
            return b""
        if len(segments) == 1:
            return segments[0]

        combined_frames = b""
        params = None
        for segment in segments:
            with wave.open(io.BytesIO(segment), "rb") as wf:
                if params is None:
                    params = wf.getparams()
                combined_frames += wf.readframes(wf.getnframes())

        if params is None:
            return b""

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
