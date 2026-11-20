"""Background thread that loads the models and processes one recording."""

from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..asr import AudioError, load_audio
from ..engines import get_engines
from ..pipeline import process_recording
from ..settings import Settings


class ProcessWorker(QThread):
    status = Signal(str)  # free text: downloading / loading / reading
    progress = Signal(str, float)  # stage, fraction 0..1
    segment = Signal(object)  # store.Segment
    done = Signal(object)  # store.ClassRecord
    cancelled_run = Signal()
    failed = Signal(str)

    def __init__(self, audio_path: str, title: str, date: str, settings: Settings,
                 class_id: str | None = None, parent=None):
        super().__init__(parent)
        self.audio_path, self.title, self.date = audio_path, title, date
        self.settings, self.class_id = settings, class_id
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            self.status.emit("Reading audio...")
            audio = load_audio(self.audio_path)
            asr, tr = get_engines(self.settings, progress=self.status.emit)
            if self._cancel:
                self.cancelled_run.emit()
                return
            self.status.emit("Processing...")
            rec = process_recording(
                audio, str(Path(self.audio_path).resolve()), self.title, self.date,
                Path(self.settings.library_dir), asr, tr, self.settings,
                on_segment=self.segment.emit,
                on_progress=self.progress.emit,
                cancelled=lambda: self._cancel,
                class_id=self.class_id,
            )
            if rec is None:
                self.cancelled_run.emit()
            else:
                self.done.emit(rec)
        except AudioError as e:
            self.failed.emit(str(e))
        except Exception as e:  # keep the app alive, show the cause
            if self._cancel:  # e.g. the model conversion was stopped by Cancel
                self.cancelled_run.emit()
                return
            traceback.print_exc()
            self.failed.emit(f"{type(e).__name__}: {e}")
