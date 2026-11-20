"""Sentence splitting and literal Urdu -> English translation with NLLB (no LLM)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Protocol

_HARD_STOPS = "۔؟!?"
# Words that end in "." without ending the sentence (lower-case, without the dot).
_ABBREVIATIONS = {"dr", "mr", "mrs", "ms", "prof", "st", "sr", "jr", "vs", "etc", "no", "sh"}
_CLAUSE = re.compile(r"[^،,]*[،,]+|[^،,]+$")


def _has_words(s: str) -> bool:
    return any(ch.isalnum() for ch in s)


def _pack(parts: list[str], max_chars: int) -> list[str]:
    """Greedily join consecutive parts with spaces while staying within max_chars."""
    out: list[str] = []
    for p in parts:
        if out and len(out[-1]) + 1 + len(p) <= max_chars:
            out[-1] = out[-1] + " " + p
        else:
            out.append(p)
    return out


def _fit(piece: str, max_chars: int) -> list[str]:
    if len(piece) <= max_chars:
        return [piece]
    clauses = [c.strip() for c in _CLAUSE.findall(piece) if c.strip()]
    if len(clauses) > 1:
        fitted = [f for c in clauses for f in _fit(c, max_chars)]
        return _pack(fitted, max_chars)
    words = piece.split()
    if len(words) == 1:  # one giant token: hard cut
        return [piece[i:i + max_chars] for i in range(0, len(piece), max_chars)]
    return _pack(words, max_chars)


def _sentences(text: str) -> list[str]:
    """Cut after ۔ ؟ ! ? always, and after "." only where it ends a sentence: not inside
    3.5 or www.site.com (no space follows), not after Dr. / e.g. / single initials."""
    out: list[str] = []
    start = i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch not in _HARD_STOPS and ch != ".":
            i += 1
            continue
        end = i + 1
        while end < n and (text[end] in _HARD_STOPS or text[end] == "."):
            end += 1
        if not any(c in _HARD_STOPS for c in text[i:end]):  # only dots
            words = text[start:i].split()
            word = words[-1] if words else ""
            next_ch = text[end] if end < n else " "
            if (not next_ch.isspace() or "." in word or word.lower() in _ABBREVIATIONS
                    or (len(word) == 1 and word.isalpha())):
                i = end
                continue
        out.append(text[start:end])
        start = i = end
    out.append(text[start:])
    return out


def split_sentences(texts: list[str], max_chars: int = 300) -> list[str]:
    """Split Whisper segment texts into sentences small enough for the translator.

    Splits on Urdu/English sentence marks (kept), then breaks over-long pieces at
    commas (، ,) and finally at word boundaries. Pieces without any letters are dropped.
    """
    out: list[str] = []
    for text in texts:
        for m in _sentences(text):
            piece = m.strip()
            if piece and _has_words(piece):
                out.extend(_fit(piece, max_chars))
    return out


# Replacements applied to each Urdu sentence before translation (the stored Urdu stays as
# heard). Two kinds: Whisper mis-spellings mapped back to the real word, and terms NLLB gets
# wrong, given a fixed English form it passes through unchanged. Found on real class audio.
DEFAULT_TERMS = """\
# Before translating, replace (left) with (right). One per line. The Urdu shown in the notes is not changed.
# Honorifics NLLB turns into "the Prophet"
حضرت = Hazrat
# The ﷺ symbol makes NLLB drop words ("the Messenger's house" -> "the House of Allah")
رسول اللہ صلی اللہ علیہ وآلہ وسلم = Rasulullah (SAW)
رسول اللہ صلی اللہ علیہ وسلم = Rasulullah (SAW)
رسول اللہ ﷺ = Rasulullah (SAW)
رسول اللہ = Rasulullah (SAW)
صلی اللہ علیہ وآلہ وسلم = (SAW)
صلی اللہ علیہ وسلم = (SAW)
ﷺ = (SAW)
# Whisper mis-spellings -> correct word
حجرت = ہجرت
مشرقین = مشرکین
ختل = قتل
خریب = قریب
خوریش = Quraysh
خریش = Quraysh
قریش = Quraysh
محاجر = Muhajir
مہاجر = Muhajir
انصار = Ansar
# Phrases NLLB mistranslates badly
نعوذ باللہ = (God forbid)
نعوذباللہ = (God forbid)
نوز باللہ = (God forbid)
نوزباللہ = (God forbid)
ظہر = Zuhr
"""

# Arabic-script vowel marks (zer, zabar, ...) count as part of the word they follow.
_MARKS = "[ً-ٰٟۖ-ۭ]*"


def parse_terms(text: str) -> list[tuple[str, str]]:
    """Parse 'source = replacement' lines; longest sources first so phrases win over words."""
    terms = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        src, _, dst = line.partition("=")
        if src.strip():
            terms.append((src.strip(), dst.strip()))
    return sorted(terms, key=lambda t: len(t[0]), reverse=True)


# Mishearings that are only safe to fix when the segment is about a given topic:
# (heard word, real word, words that show the topic). Whisper turbo writes ظہر (the Zuhr
# prayer) as زہر ("poison"); in a passage about prayer it is always Zuhr.
_PRAYER_CUES = ("نماز", "رکعت", "رکعتیں", "رکاتیں", "رکاتوں", "رکعتوں", "جمعہ", "جمعے",
                "فجر", "عصر", "مغرب", "عشاء", "عشا", "اذان", "فرض", "سنت", "قضا", "وتر")
CONTEXT_FIXES = [("زہر", "ظہر", _PRAYER_CUES)]


def _has_word(text: str, word: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(word) + _MARKS + r"(?!\w)", text) is not None


def apply_context_fixes(sentence: str, segment_text: str) -> str:
    """Fix context-dependent mishearings in `sentence` using the whole segment as context."""
    for heard, real, cues in CONTEXT_FIXES:
        if _has_word(sentence, heard) and any(_has_word(segment_text, c) for c in cues):
            sentence = re.sub(r"(?<!\w)" + re.escape(heard) + r"(?!\w)", real, sentence)
    return sentence


@lru_cache(maxsize=8)
def _terms_pattern(sources: tuple[str, ...]) -> re.Pattern:
    alts = "|".join(re.escape(s) for s in sources)  # longest first, so phrases win
    return re.compile(r"(?<!\w)(" + alts + ")" + _MARKS + r"(?!\w)")


def apply_terms(sentence: str, terms: list[tuple[str, str]]) -> str:
    """Replace whole words/phrases in one pass (a replacement is never replaced again)."""
    if not terms:
        return sentence
    table: dict[str, str] = {}
    for src, dst in terms:
        table.setdefault(src, dst)
    pattern = _terms_pattern(tuple(src for src, _ in terms))
    return pattern.sub(lambda m: table[m.group(1)], sentence)


class Translator(Protocol):
    def translate(self, sentences: list[str]) -> list[str]:
        """Return one English sentence per input, same order."""


class NllbTranslator:
    """NLLB-200 distilled 600M via CTranslate2, translated sentence by sentence."""

    SRC = "urd_Arab"
    TGT = "eng_Latn"

    def __init__(self, model_dir: Path, device: str = "cuda", batch_size: int = 64):
        import ctranslate2
        import sentencepiece as spm

        compute = "int8_float16" if device == "cuda" else "int8"
        self._tr = ctranslate2.Translator(str(model_dir), device=device, compute_type=compute)
        self._sp = spm.SentencePieceProcessor(model_file=str(Path(model_dir) / "sentencepiece.bpe.model"))
        self._batch = batch_size

    def translate(self, sentences: list[str]) -> list[str]:
        if not sentences:
            return []
        # NLLB input format: <src_lang> pieces... </s>; CTranslate2 maps pieces to ids itself.
        src = [[self.SRC] + self._sp.encode(s, out_type=str) + ["</s>"] for s in sentences]
        results = self._tr.translate_batch(
            src,
            target_prefix=[[self.TGT]] * len(src),
            max_batch_size=self._batch,  # CTranslate2 sorts by length and batches internally
            beam_size=4,
            max_decoding_length=256,
            # Stops degenerate loops ("no, no, no, ...", "the Companions of the Companions...")
            no_repeat_ngram_size=4,
            repetition_penalty=1.1,
        )
        out: list[str] = []
        for r in results:
            tokens = [t for t in r.hypotheses[0] if t not in (self.TGT, "</s>")]
            out.append(self._sp.decode(tokens).strip())
        return out
