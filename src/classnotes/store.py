"""Class records on disk: segments.json (source of truth), notes.md and .srt exports."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path

SEGMENTS_FILE = "segments.json"
LANG_LABEL = {"ur": "Urdu", "en": "English", "ar": "Recitation"}


@dataclass
class Segment:
    id: int
    start: float
    end: float
    lang: str  # "ur" | "en" | "ar"
    lang_conf: float
    source: str  # what was said, in its own script
    text: str  # machine English ("" for recitation)
    text_edited: str | None = None  # human correction; never replaces `text`
    surah: str | None = None
    topic: str | None = None


@dataclass
class ClassRecord:
    class_id: str
    title: str
    date: str
    audio_path: str
    duration_s: float
    models: dict
    created_at: str
    segments: list[Segment] = field(default_factory=list)
    schema_version: int = 1


def display_text(seg: Segment) -> str:
    return seg.text_edited if seg.text_edited else seg.text


def class_dir(library: Path, class_id: str) -> Path:
    return Path(library) / class_id


def new_class_id(library: Path, date: str) -> str:
    library = Path(library)
    if not (library / date).exists():
        return date
    n = 2
    while (library / f"{date}-{n}").exists():
        n += 1
    return f"{date}-{n}"


def _pick(cls, data: dict) -> dict:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in names}


def record_from_dict(data: dict) -> ClassRecord:
    segs = [Segment(**_pick(Segment, s)) for s in data.get("segments", [])]
    return ClassRecord(**{**_pick(ClassRecord, data), "segments": segs})


def load_record(folder: Path) -> ClassRecord:
    data = json.loads((Path(folder) / SEGMENTS_FILE).read_text("utf-8"))
    return record_from_dict(data)


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, "utf-8")
    os.replace(tmp, path)


def save_record(rec: ClassRecord, library: Path, backup: bool = False) -> Path:
    """Write segments.json atomically, plus notes.md and <class_id>.srt.

    With backup=True an existing segments.json is first kept as segments.<timestamp>.json
    (used when re-processing, so earlier machine output is never lost).
    """
    folder = class_dir(library, rec.class_id)
    folder.mkdir(parents=True, exist_ok=True)
    seg_path = folder / SEGMENTS_FILE
    if backup and seg_path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = folder / f"segments.{stamp}.json"
        n = 2
        while dest.exists():
            dest = folder / f"segments.{stamp}-{n}.json"
            n += 1
        shutil.copy2(seg_path, dest)
    _write_atomic(seg_path, json.dumps(asdict(rec), ensure_ascii=False, indent=2))
    _write_atomic(folder / "notes.md", render_notes_md(rec))
    _write_atomic(folder / f"{rec.class_id}.srt", render_srt(rec))
    return folder


def list_library(library: Path) -> list[ClassRecord]:
    library = Path(library)
    if not library.is_dir():
        return []
    recs = []
    for d in library.iterdir():
        if (d / SEGMENTS_FILE).is_file():
            try:
                recs.append(load_record(d))
            except (OSError, ValueError, TypeError, KeyError):
                continue
    return sorted(recs, key=lambda r: (r.date, r.class_id), reverse=True)


def fmt_clock(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def _fmt_srt(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def render_notes_md(rec: ClassRecord) -> str:
    lines = [f"# {rec.title or rec.class_id}", "", f"{rec.date} · {Path(rec.audio_path).name}", ""]
    if not rec.segments:
        lines.append("_No speech found._")
    for seg in rec.segments:
        label = LANG_LABEL.get(seg.lang, seg.lang)
        head = f"**[{fmt_clock(seg.start)}]** *({label})*"
        if seg.lang == "ar":
            lines.append(f"{head} {seg.source}")
        else:
            edited = " _(edited)_" if seg.text_edited else ""
            lines.append(f"{head} {display_text(seg)}{edited}")
            if seg.lang != "en":
                lines.append(f"> {seg.source}")
        lines.append("")
    return "\n".join(lines)


def render_srt(rec: ClassRecord) -> str:
    blocks = []
    for seg in rec.segments:
        text = display_text(seg)
        if seg.lang == "ar" or not text.strip():
            continue
        n = len(blocks) + 1
        blocks.append(f"{n}\n{_fmt_srt(seg.start)} --> {_fmt_srt(seg.end)}\n{text}\n")
    return "\n".join(blocks)
