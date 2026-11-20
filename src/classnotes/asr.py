"""Audio loading and the Whisper (faster-whisper) wrapper used by the pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

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


ChooseFn = Callable[[list[tuple[str, float]], int], tuple[str, float]]
BlockResult = tuple[str, float, list[str]]  # (language, confidence, texts)


class Asr(Protocol):
    def speech_spans(self, audio: np.ndarray) -> list[tuple[int, int]]: ...

    def transcribe_batch(self, clips: list[np.ndarray], prompts: dict[str, str | None],
                         choose: ChooseFn) -> list[BlockResult]:
        """Per clip: detect the language, let `choose` decide, transcribe in that language."""

    def transcribe(self, clip: np.ndarray, lang: str, prompt: str | None) -> list[str]:
        """Slow, careful transcription of one clip (with temperature fallback)."""


# A batch result this repetitive or this unsure is redone with the careful transcribe().
MAX_COMPRESSION = 2.4
MIN_AVG_LOGPROB = -1.0


class WhisperAsr:
    def __init__(self, model_dir: Path, device: str, settings: Settings):
        from faster_whisper import WhisperModel
        from faster_whisper.tokenizer import Tokenizer
        from faster_whisper.transcribe import get_suppressed_tokens

        compute = "float16" if device == "cuda" else "int8"
        self.model = WhisperModel(str(model_dir), device=device, compute_type=compute)
        self.settings = settings
        m = self.model
        self._tok = {lang: Tokenizer(m.hf_tokenizer, m.model.is_multilingual, task="transcribe",
                                     language=lang) for lang in ("ur", "en", "ar")}
        self._suppress = list(get_suppressed_tokens(self._tok["ur"], [-1]))

    def _prompt(self, lang: str, text: str | None) -> list[int]:
        tok = self._tok[lang]
        previous = tok.encode(" " + text.strip()) if text and text.strip() else []
        return self.model.get_prompt(tok, previous, without_timestamps=False)

    def _decode(self, lang: str, ids: list[int]) -> list[str]:
        """Token ids -> phrases, split at Whisper's timestamp tokens."""
        tok = self._tok[lang]
        parts, cur = [], []
        for t in ids:
            if t >= tok.timestamp_begin:
                if cur:
                    parts.append(tok.decode(cur))
                    cur = []
            elif t < tok.eot:
                cur.append(t)
        if cur:
            parts.append(tok.decode(cur))
        return [p.strip() for p in parts if p.strip()]

    def transcribe_batch(self, clips: list[np.ndarray], prompts: dict[str, str | None],
                         choose: ChooseFn) -> list[BlockResult]:
        try:
            return self._batch(clips, prompts, choose)
        except RuntimeError as e:
            if "out of memory" not in str(e).lower() or len(clips) == 1:
                raise
            half = len(clips) // 2  # smaller GPU: split the batch and carry on
            return (self.transcribe_batch(clips[:half], prompts, choose)
                    + self.transcribe_batch(clips[half:], prompts, choose))

    def _batch(self, clips, prompts, choose) -> list[BlockResult]:
        from faster_whisper.audio import pad_or_trim
        from faster_whisper.transcribe import get_compression_ratio

        m = self.model
        feats = np.stack([pad_or_trim(m.feature_extractor(c)[..., :-1]) for c in clips])
        enc = m.encode(feats)  # one encoder pass serves language detection and decoding
        detected = m.model.detect_language(enc)
        langs = [choose([(t[2:-2], p) for t, p in probs], len(c)) for probs, c in zip(detected, clips)]
        results = m.model.generate(
            enc, [self._prompt(lang, prompts.get(lang)) for lang, _ in langs],
            beam_size=5, patience=1, length_penalty=1, max_length=m.max_length,
            suppress_blank=True, suppress_tokens=self._suppress, return_scores=True,
        )
        out: list[BlockResult] = []
        for clip, (lang, conf), r in zip(clips, langs, results):
            ids = r.sequences_ids[0]
            texts = self._decode(lang, ids)
            avg_logprob = r.scores[0] * len(ids) / (len(ids) + 1)
            if get_compression_ratio(" ".join(texts)) > MAX_COMPRESSION or avg_logprob < MIN_AVG_LOGPROB:
                texts = self.transcribe(clip, lang, prompts.get(lang))
            out.append((lang, conf, texts))
        return out

    def speech_spans(self, audio: np.ndarray) -> list[tuple[int, int]]:
        from faster_whisper.vad import VadOptions, get_speech_timestamps

        opts = VadOptions(
            min_silence_duration_ms=self.settings.min_silence_ms,
            max_speech_duration_s=self.settings.max_speech_s,
        )
        return [(s["start"], s["end"]) for s in get_speech_timestamps(audio, opts)]

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
