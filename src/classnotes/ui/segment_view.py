"""Segment list rendered as rich text in a QTextBrowser (wraps Urdu RTL text natively)."""

from __future__ import annotations

from bisect import bisect_right
from html import escape

from ..store import Segment, display_text, fmt_clock

URDU_FONT = "'Urdu Typesetting', 'Segoe UI', 'Noto Naskh Arabic', sans-serif"

LIGHT = {
    "fg": "#1f2328", "muted": "#59636e", "hl": "#fff4d6", "rule": "#e6e8eb", "link": "#0b57d0",
    "ur": "#1a7f37", "en": "#0b57d0", "ar": "#8250df",
}
DARK = {
    "fg": "#e6edf3", "muted": "#9198a1", "hl": "#3a3216", "rule": "#30363d", "link": "#7aa7ff",
    "ur": "#3fb950", "en": "#7aa7ff", "ar": "#bc8cff",
}
BADGE = {"ur": "UR", "en": "EN", "ar": "AR"}


def segment_at(segments: list[Segment], t: float) -> int | None:
    """Index of the segment playing at time t (seconds), or None in a gap."""
    starts = [s.start for s in segments]
    i = bisect_right(starts, t) - 1
    if i >= 0 and t <= segments[i].end:
        return i
    return None


def render_segments_html(segments: list[Segment], current_id: int | None, dark: bool = False) -> str:
    c = DARK if dark else LIGHT
    css = (
        f"body {{ color: {c['fg']}; font-family: 'Segoe UI'; font-size: 10.5pt; }}"
        f"a {{ text-decoration: none; color: {c['link']}; }}"
        f".muted {{ color: {c['muted']}; }}"
        f".src {{ font-family: {URDU_FONT}; font-size: 14pt; color: {c['muted']}; }}"
    )
    if not segments:
        return f"<html><head><style>{css}</style></head><body><p class='muted'>No speech found.</p></body></html>"

    rows = []
    for seg in segments:
        bg = f' bgcolor="{c["hl"]}"' if seg.id == current_id else ""
        badge = f'<b style="color:{c[seg.lang]}">{BADGE.get(seg.lang, seg.lang.upper())}</b>'
        left = f'<a href="seek:{seg.id}"><b>{fmt_clock(seg.start)}</b></a><br>{badge}'
        if seg.lang == "ar":
            body = (
                f'<p dir="rtl" class="src">{escape(seg.source)}</p>'
                f'<p class="muted"><i>Recitation (Arabic), not translated</i></p>'
            )
        else:
            edited = ' <span class="muted"><i>(edited)</i></span>' if seg.text_edited else ""
            body = f'<p>{escape(display_text(seg))}{edited} &nbsp;<a href="edit:{seg.id}">✎</a></p>'
            if seg.lang != "en":
                body += f'<p dir="rtl" class="src">{escape(seg.source)}</p>'
        rows.append(
            f'<a name="seg-{seg.id}"></a>'
            f'<table width="100%" cellspacing="0" cellpadding="6"'
            f' style="border-bottom: 1px solid {c["rule"]};"><tr{bg}>'
            f'<td width="64" valign="top">{left}</td><td valign="top">{body}</td></tr></table>'
        )
    return f"<html><head><style>{css}</style></head><body>{''.join(rows)}</body></html>"
