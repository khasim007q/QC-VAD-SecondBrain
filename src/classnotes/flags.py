"""Which lines the reviewer should check first, and why (no models: rules on stored values)."""

from __future__ import annotations

from .store import Segment

# Calibrated on Session 19 (103 min, 421 lines, turbo batched pipeline) so about 5-10% of lines
# are flagged. The design's 0.9 language cut-off flagged 103 lines (24%): block-level detection
# scores Urdu-with-English blocks low, so it was lowered to the 5th percentile.
# Result: 40 of 421 lines (9.5%); the same class without scores (processed earlier): 32 (7.6%).
MIN_LANG_CONF = 0.45  # language detection below this: "Language unsure"
MAX_SHORT_WORDS = 2  # this many Urdu words or fewer: often noise or a cut-off word
MIN_WORD_RATIO = 0.43  # English words / Urdu words below this (2nd percentile): dropped words
MIN_ASR_LOGPROB = -0.61  # Whisper average log-probability (2nd percentile): misheard words
MIN_MT_SCORE = -1.01  # NLLB average token log-probability (2nd percentile): unsure translation


def flag_reason(seg: Segment) -> str | None:
    """The first reason this line needs checking, in plain words, or None."""
    if seg.text_edited or seg.checked or seg.lang == "ar":
        return None
    if seg.lang_conf < MIN_LANG_CONF:
        return "Language unsure"
    src_words = len(seg.source.split())
    if src_words <= MAX_SHORT_WORDS:
        return "Very short, may be noise"
    if seg.lang == "ur" and len(seg.text.split()) / src_words < MIN_WORD_RATIO:
        return "Translation may be missing words"
    if seg.asr_logprob is not None and seg.asr_logprob < MIN_ASR_LOGPROB:
        return "Words may be misheard"
    if seg.mt_score is not None and seg.mt_score < MIN_MT_SCORE:
        return "Translation unsure"
    return None


def flagged_ids(segments: list[Segment]) -> list[int]:
    return [s.id for s in segments if flag_reason(s)]


def next_flagged(segments: list[Segment], after_id: int | None) -> int | None:
    """The next flagged line after `after_id`, wrapping round (ids increase down the class)."""
    ids = flagged_ids(segments)
    if not ids:
        return None
    later = [i for i in ids if after_id is None or i > after_id]
    return later[0] if later else ids[0]
