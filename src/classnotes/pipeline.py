"""VAD -> language per span -> merge -> transcribe (en/ar) or transcribe + translate (ur)."""

from __future__ import annotations

from typing import Callable

import numpy as np

from .asr import Asr
from .segment import SR, LangSpan, bucket_probs, choose_lang, merge_spans
from .settings import Settings
from .store import Segment
from .translate import Translator, apply_terms, parse_terms, split_sentences

ProgressFn = Callable[[str, float], None]


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

    lang_spans: list[LangSpan] = []
    for i, (a, b) in enumerate(spans):
        if cancelled():
            return None
        lang, conf = choose_lang(
            bucket_probs(asr.lang_probs(audio[a:b])),
            b - a,
            min_conf=settings.min_conf,
            min_dur_s=settings.min_dur_s,
        )
        lang_spans.append(LangSpan(a, b, lang, conf))
        on_progress("Detecting language", (i + 1) / len(spans))

    merged = merge_spans(lang_spans, max_gap_s=settings.merge_gap_s, max_len_s=settings.merge_max_s)
    terms = parse_terms(settings.terms)
    total = sum(s.end - s.start for s in merged)
    done = 0
    segments: list[Segment] = []
    on_progress("Transcribing", 0.0)

    for span in merged:
        if cancelled():
            return None
        prompt = None if span.lang == "ar" else (settings.glossary or None)
        texts = [t.strip() for t in asr.transcribe(audio[span.start:span.end], span.lang, prompt)]
        texts = [t for t in texts if t]
        seg = _make_segment(len(segments), span, texts, translator, terms)
        if seg is not None:
            segments.append(seg)
            on_segment(seg)
        done += span.end - span.start
        on_progress("Transcribing", done / total)

    return segments


def _make_segment(idx: int, span: LangSpan, texts: list[str], translator: Translator,
                  terms: list[tuple[str, str]] = ()) -> Segment | None:
    if not texts:
        return None
    if span.lang == "ur":
        sentences = split_sentences(texts)
        if not sentences:
            return None
        source = " ".join(sentences)  # stored exactly as heard
        text = " ".join(translator.translate([apply_terms(s, terms) for s in sentences]))
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


MODEL_NAMES = {"asr": "whisper-large-v3", "mt": "nllb-200-distilled-600M-ct2-int8"}


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
        models=dict(MODEL_NAMES),
        created_at=datetime.now().isoformat(timespec="seconds"),
        segments=segments,
    )
    store.save_record(rec, library, backup=class_id is not None)
    return rec
