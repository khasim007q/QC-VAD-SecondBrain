"""Process a recording without the window:

    uv run python -m classnotes.cli "D:/Quran class/2026-11-18.m4a" --title "Al-Kahf 1-10"
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date as _date
from pathlib import Path

from . import store
from .asr import AudioError, load_audio
from .engines import get_engines
from .pipeline import process_recording
from .settings import Settings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Urdu/English class recording -> English notes")
    ap.add_argument("audio")
    ap.add_argument("--title", default="")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: file date)")
    ap.add_argument("--library", default=None)
    ap.add_argument("--device", choices=["auto", "cuda", "cpu"], default=None)
    ap.add_argument("--reprocess", metavar="CLASS_ID", default=None,
                    help="re-process an existing class (its current notes are kept as a backup)")
    args = ap.parse_args(argv)

    settings = Settings.load()
    if args.device:
        settings.device = args.device
    library = Path(args.library or settings.library_dir)
    path = Path(args.audio)
    try:
        audio = load_audio(path)
    except AudioError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    day = args.date or _date.fromtimestamp(path.stat().st_mtime).isoformat()
    if args.reprocess:
        old = store.load_record(store.class_dir(library, args.reprocess))
        day, args.title = old.date, args.title or old.title

    asr, tr = get_engines(settings, progress=print)
    t0 = time.time()
    last = [""]

    def on_progress(stage: str, frac: float) -> None:
        line = f"{stage}: {frac:5.0%}"
        if line != last[0]:
            print("\r" + line, end="", flush=True)
            last[0] = line

    def on_segment(seg: store.Segment) -> None:
        print(f"\r[{store.fmt_clock(seg.start)}] ({seg.lang}) {seg.text or seg.source}")

    rec = process_recording(
        audio, str(path.resolve()), args.title or path.stem, day,
        library, asr, tr, settings, on_segment, on_progress, cancelled=lambda: False,
        class_id=args.reprocess,
    )
    folder = store.class_dir(library, rec.class_id)
    print(f"\nDone in {time.time() - t0:.0f}s: {len(rec.segments)} segments -> {folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
