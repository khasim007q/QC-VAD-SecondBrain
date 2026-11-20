"""Export a class in every supported format. English means the reviewer's edit where there is one."""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import asdict
from html import escape
from pathlib import Path

from . import store
from .flags import flag_reason
from .store import ClassRecord, display_text, fmt_clock

FORMATS: list[tuple[str, str, str]] = [
    ("md", "Notes", ".md"),
    ("docx", "Word document", ".docx"),
    ("pdf", "PDF", ".pdf"),
    ("srt", "Subtitles", ".srt"),
    ("vtt", "Web subtitles", ".vtt"),
    ("txt", "Plain text", ".txt"),
    ("csv", "Spreadsheet", ".csv"),
    ("json", "Data for search tools", ".json"),
]

URDU_FONT = "Noto Nastaliq Urdu"
ARABIC_FONT = "Noto Naskh Arabic"
_FORBIDDEN = re.compile(r'[\\/:*?"<>|]')


def default_name(rec: ClassRecord, ext: str) -> str:
    title = " ".join(_FORBIDDEN.sub("", rec.title or "").split())
    return (f"{rec.class_id} {title}" if title else rec.class_id) + ext


def _cues(rec: ClassRecord) -> list[tuple[float, float, str]]:
    """Subtitle cues: no recitation, no empty lines, blank lines inside an edit removed."""
    out = []
    for seg in rec.segments:
        text = "\n".join(ln.strip() for ln in display_text(seg).splitlines() if ln.strip())
        if seg.lang != "ar" and text:
            out.append((seg.start, seg.end, text))
    return out


def _vtt(rec: ClassRecord) -> str:
    def ts(t: float) -> str:
        return store._fmt_srt(t).replace(",", ".")

    blocks = ["WEBVTT\n"] + [f"{ts(a)} --> {ts(b)}\n{text}\n" for a, b, text in _cues(rec)]
    return "\n".join(blocks)


def _txt(rec: ClassRecord) -> str:
    lines = [rec.title or rec.class_id, rec.date, ""]
    for seg in rec.segments:
        if seg.lang == "ar":
            lines.append(f"[{fmt_clock(seg.start)}] (Recitation) {seg.source}")
        elif display_text(seg).strip():
            lines.append(f"[{fmt_clock(seg.start)}] {' '.join(display_text(seg).split())}")
    return "\n".join(lines) + "\n"


def _csv(rec: ClassRecord) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["start", "end", "language", "urdu", "english_machine", "english_edited", "flag"])
    for seg in rec.segments:
        w.writerow([seg.start, seg.end, seg.lang, seg.source, seg.text, seg.text_edited or "",
                    flag_reason(seg) or ""])
    return buf.getvalue()


def _docx(rec: ClassRecord, path: Path) -> None:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    def rtl_paragraph(text: str, font: str):
        p = doc.add_paragraph()
        p._p.get_or_add_pPr().append(OxmlElement("w:bidi"))
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run = p.add_run(text)
        rpr = run._r.get_or_add_rPr()
        fonts = OxmlElement("w:rFonts")
        fonts.set(qn("w:cs"), font)
        rpr.insert(0, fonts)
        rpr.append(OxmlElement("w:rtl"))
        return p

    doc = docx.Document()
    doc.add_heading(rec.title or rec.class_id, level=1)
    doc.add_paragraph(f"{rec.date} · {fmt_clock(rec.duration_s)}")
    if not rec.segments:
        doc.add_paragraph("No speech found.")
    for seg in rec.segments:
        p = doc.add_paragraph()
        p.add_run(fmt_clock(seg.start) + "  ").bold = True
        if seg.lang == "ar":
            p.add_run("Recitation, not translated")
            rtl_paragraph(seg.source, ARABIC_FONT)
            continue
        p.add_run(display_text(seg))
        if seg.lang != "en":
            rtl_paragraph(seg.source, URDU_FONT)
    doc.save(str(path))


def _pdf(rec: ClassRecord, path: Path) -> None:
    from PySide6.QtGui import QPageSize, QPdfWriter, QTextDocument

    rows = [f"<h1>{escape(rec.title or rec.class_id)}</h1><p>{rec.date} · {fmt_clock(rec.duration_s)}</p>"]
    if not rec.segments:
        rows.append("<p>No speech found.</p>")
    for seg in rec.segments:
        head = f"<b>{fmt_clock(seg.start)}</b>&nbsp;&nbsp;"
        if seg.lang == "ar":
            rows.append(f"<p>{head}Recitation, not translated</p>"
                        f"<p dir='rtl' style=\"font-family:'{ARABIC_FONT}'\">{escape(seg.source)}</p>")
            continue
        rows.append(f"<p>{head}{escape(display_text(seg))}</p>")
        if seg.lang != "en":
            rows.append(f"<p dir='rtl' style=\"font-family:'{URDU_FONT}','Urdu Typesetting'; font-size:13pt\">"
                        f"{escape(seg.source)}</p>")
    doc = QTextDocument()
    doc.setHtml("<html><body style='font-size:11pt'>" + "".join(rows) + "</body></html>")
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setResolution(300)
    writer.setTitle(rec.title or rec.class_id)
    doc.print_(writer)


def export(rec: ClassRecord, kind: str, path: Path) -> None:
    path = Path(path)
    if kind == "md":
        path.write_text(store.render_notes_md(rec), "utf-8")
    elif kind == "srt":
        path.write_text(store.render_srt(rec), "utf-8")
    elif kind == "vtt":
        path.write_text(_vtt(rec), "utf-8")
    elif kind == "txt":
        path.write_text(_txt(rec), "utf-8")
    elif kind == "csv":
        path.write_text(_csv(rec), "utf-8-sig", newline="")
    elif kind == "json":
        path.write_text(json.dumps(asdict(rec), ensure_ascii=False, indent=2), "utf-8")
    elif kind == "docx":
        _docx(rec, path)
    elif kind == "pdf":
        _pdf(rec, path)
    else:
        raise ValueError(f"unknown export format {kind!r}")
