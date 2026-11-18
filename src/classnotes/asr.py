"""Audio loading and the Whisper (faster-whisper) wrapper used by the pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np

from .settings import Settings

SR = 16000


class AudioError(Exception):
    """The recording could not be read."""


def _decode(path: Path) -> np.ndarray:
    """Decode any audio/video file to 16 kHz mono float32 with PyAV."""
    import av

    chunks: list[np.ndarray] = []
    with av.open(str(path)) as container:
        streams = [s for s in container.streams if s.type == "audio"]
        if not streams:
            raise AudioError(f"{path.name} has no audio track")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=SR)
        for frame in container.decode(streams[0]):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def load_audio(path: str | Path) -> np.ndarray:
    p = Path(path)
    if not p.is_file():
        raise AudioError(f"File not found: {p}")
    try:
        audio = _decode(p)
    except AudioError:
        raise
    except Exception as e:  # PyAV raises a variety of errors
        raise AudioError(f"Could not read audio from {p.name}: {e}") from e
    if audio.size == 0:
        raise AudioError(f"{p.name} contains no audio")
    return audio


class Asr(Protocol):
    def speech_spans(self, audio: np.ndarray) -> list[tuple[int, int]]: ...
    def lang_probs(self, clip: np.ndarray) -> list[tuple[str, float]]: ...
    def transcribe(self, clip: np.ndarray, lang: str, prompt: str | None) -> list[str]: ...


class WhisperAsr:
    def __init__(self, model_dir: Path, device: str, settings: Settings):
        from faster_whisper import WhisperModel

        compute = "float16" if device == "cuda" else "int8"
        self.model = WhisperModel(str(model_dir), device=device, compute_type=compute)
        self.settings = settings

    def speech_spans(self, audio: np.ndarray) -> list[tuple[int, int]]:
        from faster_whisper.vad import VadOptions, get_speech_timestamps

        opts = VadOptions(
            min_silence_duration_ms=self.settings.min_silence_ms,
            max_speech_duration_s=self.settings.max_speech_s,
        )
        return [(s["start"], s["end"]) for s in get_speech_timestamps(audio, opts)]

    def lang_probs(self, clip: np.ndarray) -> list[tuple[str, float]]:
        _, _, probs = self.model.detect_language(clip)
        return probs

    def transcribe(self, clip: np.ndarray, lang: str, prompt: str | None) -> list[str]:
        segments, _ = self.model.transcribe(
            clip,
            language=lang,
            task="transcribe",
            beam_size=5,
            condition_on_previous_text=False,
            initial_prompt=prompt or None,
            vad_filter=False,
        )
        return [s.text for s in segments]
