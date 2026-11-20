"""VAD -> merge close spans into blocks (<= ~25 s) -> in batches of blocks: one Whisper
encoder pass gives both the language and the transcript -> Urdu sentences translated with
NLLB, one call per batch. English is kept verbatim, Arabic recitation is marked."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

import numpy as np

from .asr import Asr
from .segment import SR, LangSpan, bucket_probs, choose_lang, merge_spans
from .settings import Settings
from .store import Segment
from .translate import Translator, apply_context_fixes, apply_terms, parse_terms, split_sentences

ProgressFn = Callable[[str, float], None]

MAX_BLOCK_S = 29.0  # Whisper sees 30 s at a time; anything longer would be cut off
URDU_SCRIPT_LIMIT = 10  # more Urdu letters than this in an "English" block -> it was Urdu


def _blocks(spans: list[tuple[int, int]], settings: Settings) -> list[LangSpan]:
    """Merge VAD spans with short gaps (language-agnostic), never longer than MAX_BLOCK_S."""
    raw = [LangSpan(a, b, "", 1.0) for a, b in spans]
    merged = merge_spans(raw, max_gap_s=settings.merge_gap_s,
                         max_len_s=min(settings.merge_max_s, MAX_BLOCK_S))
    limit = int(MAX_BLOCK_S * SR)
    out: list[LangSpan] = []
    for b in merged:  # a single VAD span can still be too long: cut it evenly
        n = -(-(b.end - b.start) // limit)
        step = -(-(b.end - b.start) // n)
        out += [replace(b, start=a, end=min(a + step, b.end)) for a in range(b.start, b.end, step)]
    return out


def _urdu_letters(texts: list[str]) -> int:
    return sum("؀" <= ch <= "ۿ" for t in texts for ch in t)


def run_pipeline(
    audio: np.ndarray,
    asr: Asr,
    translator: Translator,
    settings: Settings,
    on_segment: Callable[[Segment], None],
    on_progress: ProgressFn,
    cancelled: Callable[[], bool],
) -> list[Segment] | None:
    """Process one recording. Returns the segments, or None if cancelled."""
    on_progress("Finding speech", 0.0)
    spans = asr.speech_spans(audio)
    if not spans:
        on_progress("Done", 1.0)
        return []

    blocks = _blocks(spans, settings)
    terms = parse_terms(settings.terms)
    glossary = settings.glossary or None
    prompts = {"ur": glossary, "en": glossary, "ar": None}

    def choose(probs, n_samples):
        return choose_lang(bucket_probs(probs), n_samples,
                           min_conf=settings.min_conf, min_dur_s=settings.min_dur_s)

    segments: list[Segment] = []
    bs = max(1, int(settings.batch_size))
    on_progress("Transcribing", 0.0)
    for j in range(0, len(blocks), bs):
        if cancelled():
            return None
        chunk = blocks[j:j + bs]
        clips = [audio[b.start:b.end] for b in chunk]
        heard = []
        for b, clip, (lang, conf, texts, logprob) in zip(chunk, clips,
                                                         asr.transcribe_batch(clips, prompts, choose)):
            texts = [t.strip() for t in texts if t.strip()]
            if lang == "en" and _urdu_letters(texts) > URDU_SCRIPT_LIMIT:
                lang = "ur"  # mixed speech the detector called English, but it is Urdu
                texts = [t.strip() for t in asr.transcribe(clip, "ur", prompts["ur"]) if t.strip()]
                logprob = None
            heard.append((replace(b, lang=lang, conf=conf), texts, logprob))
        for seg in _make_segments(len(segments), heard, translator, terms):
            segments.append(seg)
            on_segment(seg)
        on_progress("Transcribing", min(j + bs, len(blocks)) / len(blocks))

    return segments


def _make_segments(first_id: int, heard: list[tuple[LangSpan, list[str], float | None]],
                   translator: Translator, terms) -> list[Segment]:
    """Build segments for one batch; all its Urdu sentences go to the translator in one call."""
    sentences = {i: split_sentences(texts) for i, (span, texts, _) in enumerate(heard)
                 if span.lang == "ur" and texts}
    flat = [apply_terms(apply_context_fixes(s, " ".join(heard[i][1])), terms)
            for i in sentences for s in sentences[i]]
    english = iter(translator.translate_scored(flat) if flat else [])
    out: list[Segment] = []
    for i, (span, texts, logprob) in enumerate(heard):
        scored = [next(english) for _ in sentences.get(i, [])]
        seg = _make_segment(first_id + len(out), span, texts, [t for t, _ in scored], sentences.get(i))
        if seg is not None:
            seg.asr_logprob = None if logprob is None else round(logprob, 3)
            if scored:
                seg.mt_score = round(sum(sc for _, sc in scored) / len(scored), 3)
            out.append(seg)
    return out


def _make_segment(idx: int, span: LangSpan, texts: list[str], translated: list[str],
                  sentences: list[str] | None) -> Segment | None:
    if not texts:
        return None
    if span.lang == "ur":
        if not sentences:
            return None
        source = " ".join(sentences)  # stored exactly as heard
        text = " ".join(translated)
    elif span.lang == "en":
        source = text = " ".join(texts)
    else:  # Arabic recitation: keep as heard, never translate
        source, text = " ".join(texts), ""
    return Segment(
        id=idx,
        start=round(span.start / SR, 2),
        end=round(span.end / SR, 2),
        lang=span.lang,
        lang_conf=round(span.conf, 3),
        source=source,
        text=text,
    )


MT_MODEL_NAME = "nllb-200-distilled-600M-ct2-int8"


def process_recording(
    audio: np.ndarray,
    audio_path: str,
    title: str,
    date: str,
    library,
    asr: Asr,
    translator: Translator,
    settings: Settings,
    on_segment: Callable[[Segment], None],
    on_progress: ProgressFn,
    cancelled: Callable[[], bool],
    class_id: str | None = None,
):
    """Run the pipeline and save the class. Returns the ClassRecord, or None if cancelled.

    Passing an existing class_id re-processes that class; its previous segments.json is
    kept as a timestamped backup.
    """
    from datetime import datetime
    from pathlib import Path

    from . import store

    segments = run_pipeline(audio, asr, translator, settings, on_segment, on_progress, cancelled)
    if segments is None:
        return None
    library = Path(library)
    rec = store.ClassRecord(
        class_id=class_id or store.new_class_id(library, date),
        title=title,
        date=date,
        audio_path=str(audio_path),
        duration_s=round(len(audio) / SR, 2),
        models={"asr": f"whisper-{settings.whisper_model}", "mt": MT_MODEL_NAME},
        created_at=datetime.now().isoformat(timespec="seconds"),
        segments=segments,
    )
    store.save_record(rec, library, backup=class_id is not None)
    return rec
