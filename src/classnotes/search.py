"""Search every class's lines: English (edit and machine), Urdu, and titles. Plain substring
matching on normalised text (case-folded, Arabic-script vowel marks removed)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .store import ClassRecord

_MARKS = re.compile("[ً-ٰٟۖ-ۭ]")
SNIPPET_MAX = 120


@dataclass
class Hit:
    class_id: str
    title: str
    seg_id: int  # -1 for a match in the class title
    start: float
    snippet: str
    match_start: int  # match position inside `snippet`
    match_end: int


def _normalize_map(text: str) -> tuple[str, list[int]]:
    """Normalised text plus, for each of its characters, the index in `text` it came from."""
    out: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(text):
        if _MARKS.match(ch):
            continue
        if ch.isspace():
            if out and out[-1] != " ":
                out.append(" ")
                idx.append(i)
            continue
        for c in ch.casefold():
            out.append(c)
            idx.append(i)
    while out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def normalize(text: str) -> str:
    return _normalize_map(text)[0].strip()


def _snippet(text: str, start: int, end: int) -> tuple[str, int, int]:
    """Cut at most SNIPPET_MAX characters of `text` around [start, end)."""
    if len(text) <= SNIPPET_MAX:
        return text, start, end
    room = max(0, SNIPPET_MAX - 2 - (end - start))  # 2 for the ellipses
    a = max(0, start - room // 2)
    b = min(len(text), a + (end - start) + room)
    a = max(0, b - (end - start) - room)
    pre = "…" if a > 0 else ""
    post = "…" if b < len(text) else ""
    return pre + text[a:b] + post, start - a + len(pre), end - a + len(pre)


class SearchIndex:
    def __init__(self, records: list[ClassRecord]):
        self._records = records
        self._norm: dict[tuple[int, int, str], tuple[str, list[int]]] = {}

    def _find(self, key, text: str, q: str):
        if key not in self._norm:
            self._norm[key] = _normalize_map(text)
        norm, idx = self._norm[key]
        pos = norm.find(q)
        if pos < 0:
            return None
        return idx[pos], idx[pos + len(q) - 1] + 1

    def search(self, query: str, limit: int = 200) -> list[Hit]:
        q = normalize(query)
        if sum(ch.isalnum() for ch in q) < 2:
            return []
        hits: list[Hit] = []
        for r, rec in enumerate(self._records):
            title = rec.title or rec.class_id
            m = self._find((r, -1, "title"), title, q)
            if m:
                hits.append(Hit(rec.class_id, title, -1, 0.0, *_snippet(title, *m)))
            for seg in rec.segments:
                for field in ("text_edited", "text", "source"):
                    text = getattr(seg, field) or ""
                    m = self._find((r, seg.id, field), text, q) if text else None
                    if m:
                        hits.append(Hit(rec.class_id, title, seg.id, seg.start, *_snippet(text, *m)))
                        break
                if len(hits) >= limit:
                    return hits
        return hits
