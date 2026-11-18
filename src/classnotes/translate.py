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
            )
            for r in results:
                tokens = [t for t in r.hypotheses[0] if t not in (self.TGT, "</s>")]
                out.append(self._sp.decode(tokens).strip())
        return out
