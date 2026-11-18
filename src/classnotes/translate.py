"""Sentence splitting and literal Urdu -> English translation with NLLB (no LLM)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

_SENTENCE = re.compile(r"[^۔؟!?.]*[۔؟!?.]+|[^۔؟!?.]+$")
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


def split_sentences(texts: list[str], max_chars: int = 300) -> list[str]:
    """Split Whisper segment texts into sentences small enough for the translator.

    Splits on Urdu/English sentence marks (kept), then breaks over-long pieces at
    commas (، ,) and finally at word boundaries. Pieces without any letters are dropped.
    """
    out: list[str] = []
    for text in texts:
        for m in _SENTENCE.findall(text):
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
رسول اللہ صلی اللہ علیہ وسلم = Rasulullah (SAW)
رسول اللہ ﷺ = Rasulullah (SAW)
رسول اللہ = Rasulullah (SAW)
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

_NOT_WORD_BEFORE = r"(?<!\w)"
_NOT_WORD_AFTER = r"(?!\w)"


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


def apply_terms(sentence: str, terms: list[tuple[str, str]]) -> str:
    for src, dst in terms:
        sentence = re.sub(_NOT_WORD_BEFORE + re.escape(src) + _NOT_WORD_AFTER, dst, sentence)
    return sentence


class Translator(Protocol):
    def translate(self, sentences: list[str]) -> list[str]:
        """Return one English sentence per input, same order."""


class NllbTranslator:
    """NLLB-200 distilled 600M via CTranslate2, translated sentence by sentence."""

    SRC = "urd_Arab"
    TGT = "eng_Latn"

    def __init__(self, model_dir: Path, device: str = "cuda", batch_size: int = 16):
        import ctranslate2
        import sentencepiece as spm

        compute = "int8_float16" if device == "cuda" else "int8"
        self._tr = ctranslate2.Translator(str(model_dir), device=device, compute_type=compute)
        self._sp = spm.SentencePieceProcessor(model_file=str(Path(model_dir) / "sentencepiece.bpe.model"))
        self._batch = batch_size

    def translate(self, sentences: list[str]) -> list[str]:
        out: list[str] = []
        for i in range(0, len(sentences), self._batch):
            batch = sentences[i:i + self._batch]
            # NLLB input format: <src_lang> pieces... </s>; CTranslate2 maps pieces to ids itself.
            src = [[self.SRC] + self._sp.encode(s, out_type=str) + ["</s>"] for s in batch]
            results = self._tr.translate_batch(
                src,
                target_prefix=[[self.TGT]] * len(batch),
                beam_size=4,
                max_decoding_length=256,
                # Stops degenerate loops ("no, no, no, ...", "the Companions of the Companions...")
                no_repeat_ngram_size=4,
                repetition_penalty=1.1,
            )
            for r in results:
                tokens = [t for t in r.hypotheses[0] if t not in (self.TGT, "</s>")]
                out.append(self._sp.decode(tokens).strip())
        return out
