"""Pure logic: language buckets per speech span, and merging neighbouring spans."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

SR = 16000

# Whisper language codes folded into each bucket. Urdu is often detected as Hindi.
BUCKETS = {"ur": ("ur", "hi"), "en": ("en",), "ar": ("ar",)}


@dataclass
class LangSpan:
    start: int  # sample offset at 16 kHz
    end: int
    lang: str  # "ur" | "en" | "ar"
    conf: float


def bucket_probs(probs: Iterable[tuple[str, float]]) -> dict[str, float]:
    p = dict(probs)
    return {bucket: sum(p.get(code, 0.0) for code in codes) for bucket, codes in BUCKETS.items()}


def choose_lang(
    buckets: dict[str, float],
    n_samples: int,
    sr: int = SR,
    min_conf: float = 0.7,
    min_dur_s: float = 1.5,
) -> tuple[str, float]:
    """Pick the winning bucket; unsure or too-short spans are treated as Urdu."""
    total = sum(buckets.values()) + 1e-9
    lang = max(buckets, key=buckets.get)
    conf = buckets[lang] / total
    if n_samples < min_dur_s * sr or conf < min_conf:
        return "ur", buckets.get("ur", 0.0) / total
    return lang, conf


def merge_spans(
    spans: list[LangSpan],
    sr: int = SR,
    max_gap_s: float = 1.0,
    max_len_s: float = 25.0,
) -> list[LangSpan]:
    """Join same-language neighbours separated by a short pause, up to a maximum length."""
    out: list[LangSpan] = []
    for s in spans:
        if out:
            last = out[-1]
            if (
                last.lang == s.lang
                and s.start - last.end < max_gap_s * sr
                and s.end - last.start <= max_len_s * sr
            ):
                out[-1] = replace(last, end=s.end, conf=min(last.conf, s.conf))
                continue
        out.append(replace(s))
    return out
