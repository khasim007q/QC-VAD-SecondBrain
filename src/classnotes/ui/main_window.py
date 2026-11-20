"""Main window: sidebar (search, classes), header, the list of lines, and the player bar.

Built for listening straight through and stopping to fix lines (docs/superpowers/specs/
2026-11-20-review-screen-design.md).
"""

from __future__ import annotations

import os
from html import escape
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)

from .. import export, flags, models, store
from ..settings import Settings
from . import theme
from .dialogs import AUDIO_FILTER, NewClassDialog, SettingsDialog
from .line_view import LineList
from .player import Playback, PlayerBar, step_rate
from .sidebar import Sidebar
from .worker import ProcessWorker

WELCOME = ("Add a class and choose its recording. Urdu is translated to English line by line, the "
           "teacher's English is kept as spoken, and Quran recitation is marked, not translated.\n\n"
           "Click a line to hear it. Press E to fix the line that is playing; the machine version is "
           "always kept.")


def _button(text: str, kind: str = "secondary") -> QPushButton:
    b = QPushButton(text)
    b.setProperty("kind", kind)
    b.setCursor(Qt.PointingHandCursor)
    return b


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings | None = None, persist_settings: bool = True,
                 playback: Playback | None = None):
        super().__init__()
        self.settings = settings or Settings.load()
        self.persist = persist_settings
        self.record: store.ClassRecord | None = None
        self.record_lib: Path | None = None  # library the open class lives in
        self.worker: ProcessWorker | None = None
        self.live_segments: list[store.Segment] = []
        self.current_id: int | None = None
        self._reprocess_id: str | None = None
        self._resume_after_edit = False
        self.playback = playback or Playback(self)
        if playback is not None:
            playback.setParent(self)

        self.setWindowTitle("Class Notes")
        self.setMinimumSize(1024, 700)
        self.resize(1280, 820)
        self._build()
        self._wire()
        self._shortcuts()
        self.refresh_library()

    # ================= layout =================
    def _build(self) -> None:
        self.sidebar = Sidebar()

        # header
        self.title = QLabel("Class Notes")
        self.title.setObjectName("Title")
        self.meta = QLabel("")
        self.meta.setObjectName("Meta")
        words = QVBoxLayout()
        words.setSpacing(4)
        words.addWidget(self.title)
        words.addWidget(self.meta)
        self.next_flag_btn = _button("Next line to check   F")
        self.export_btn = _button("Export")
        self.export_menu = QMenu(self)
        for kind, label, _ext in export.FORMATS:
            self.export_menu.addAction(label, lambda k=kind: self.export(k))
        self.export_btn.setMenu(self.export_menu)
        self.more_btn = _button("More")
        self.more_menu = QMenu(self)
        self.more_menu.addAction("Re-process", self.reprocess)
        self.more_menu.addAction("Open folder", self.open_folder)
        self.more_menu.addAction("Locate recording", self.locate_audio)
        self.more_btn.setMenu(self.more_menu)
        header = QFrame()
        header.setObjectName("Header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(48, 24, 48, 16)
        hl.setSpacing(12)
        hl.addLayout(words, 1)
        for b in (self.next_flag_btn, self.export_btn, self.more_btn):
            hl.addWidget(b)

        # phase 2 slot: "use this word from now on" suggestions
        self.notice = QFrame()
        self.notice.setObjectName("Notice")
        self.notice.hide()

        # missing recording
        self.banner = QFrame()
        self.banner.setObjectName("Banner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(16, 8, 8, 8)
        bl.addWidget(QLabel("The recording for this class was moved or deleted."), 1)
        locate = _button("Locate recording")
        locate.clicked.connect(self.locate_audio)
        bl.addWidget(locate)
        self.banner.hide()

        # processing
        self.proc_panel = QFrame()
        pl = QHBoxLayout(self.proc_panel)
        pl.setContentsMargins(48, 8, 48, 8)
        self.proc_status = QLabel()
        self.proc_status.setObjectName("Meta")
        self.proc_bar = QProgressBar()
        self.proc_bar.setRange(0, 1000)
        self.proc_bar.setTextVisible(False)
        self.cancel_btn = _button("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_processing)
        pl.addWidget(self.proc_status, 2)
        pl.addWidget(self.proc_bar, 3)
        pl.addWidget(self.cancel_btn)
        self.proc_panel.hide()

        # lines / welcome
        self.lines = LineList()
        self.welcome = QLabel(WELCOME)
        self.welcome.setObjectName("Empty")
        self.welcome.setWordWrap(True)
        self.welcome.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.welcome.setContentsMargins(48, 32, 48, 32)
        self.welcome.setMaximumWidth(760)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.lines)

        self.bar = PlayerBar()

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(header)
        for w in (self.notice, self.banner):
            wrap = QHBoxLayout()
            wrap.setContentsMargins(48, 12, 48, 0)
            wrap.addWidget(w)
            rl.addLayout(wrap)
        rl.addWidget(self.proc_panel)
        rl.addWidget(self.stack, 1)
        rl.addWidget(self.bar)

        main = QWidget()
        main.setObjectName("Main")
        ml = QHBoxLayout(main)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        ml.addWidget(self.sidebar)
        ml.addWidget(right, 1)
        self.setCentralWidget(main)
        self._show_welcome()

    def _wire(self) -> None:
        sb, ln, pb, bar = self.sidebar, self.lines, self.playback, self.bar
        sb.class_selected.connect(self.open_class)
        sb.hit_selected.connect(self.open_hit)
        sb.add_button.clicked.connect(self.new_class)
        sb.settings_button.clicked.connect(self.open_settings)
        ln.seek_requested.connect(self._line_clicked)
        ln.edit_started.connect(self._edit_started)
        ln.edit_saved.connect(self._edit_saved)
        ln.edit_cancelled.connect(lambda _id: self._resume())
        ln.marked_checked.connect(self.mark_checked)
        pb.line_changed.connect(self._line_changed)
        pb.position.connect(self._position)
        pb.playing_changed.connect(bar.set_playing)
        pb.outputs_changed.connect(lambda: bar.set_outputs(pb.outputs(), self.settings.audio_output))
        pb.status.connect(lambda m: self.statusBar().showMessage(m, 10000))
        pb.error.connect(lambda m: self.statusBar().showMessage(f"{m} Try another output.", 15000))
        bar.play_clicked.connect(pb.toggle)
        bar.prev_clicked.connect(pb.prev_line)
        bar.next_clicked.connect(pb.next_line)
        bar.replay_clicked.connect(pb.replay_line)
        bar.seek_requested.connect(pb.seek_ms)
        bar.stop_after_toggled.connect(self.set_stop_after)
        bar.rate_chosen.connect(self.set_rate)
        bar.output_chosen.connect(self.set_output)
        self.next_flag_btn.clicked.connect(self.next_flagged)

        pb.set_rate(self.settings.playback_rate)
        bar.set_rate(self.settings.playback_rate)
        pb.set_stop_after_line(self.settings.stop_after_line)
        bar.set_stop_after(self.settings.stop_after_line)
        pb.set_output(self.settings.audio_output)
        bar.set_outputs(pb.outputs(), self.settings.audio_output)

    def _shortcuts(self) -> None:
        keys = {
            "Space": self.playback.toggle, "Left": self.playback.prev_line, "Right": self.playback.next_line,
            "R": self.playback.replay_line, "S": lambda: self.set_stop_after(not self.settings.stop_after_line),
            "E": self.edit_playing_line, "F": self.next_flagged,
            "[": lambda: self.set_rate(step_rate(self.settings.playback_rate, -1)),
            "]": lambda: self.set_rate(step_rate(self.settings.playback_rate, 1)),
        }
        for seq, fn in keys.items():
            QShortcut(QKeySequence(seq), self, activated=lambda fn=fn: self._guarded(fn))
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.sidebar.focus_search)

    def _ask_edit(self) -> str:
        """'save', 'discard' or 'cancel' for a half-typed edit (tests replace this)."""
        box = QMessageBox(QMessageBox.Question, "Unsaved change",
                          "You are editing a line. Save the change first?",
                          QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, self)
        box.setDefaultButton(QMessageBox.Save)
        return {QMessageBox.Save: "save", QMessageBox.Discard: "discard"}.get(box.exec(), "cancel")

    def _settle_edit(self) -> bool:
        """Before anything that would replace the list: deal with an open edit. False = stay."""
        if not self.lines.is_editing():
            return True
        answer = self._ask_edit()
        if answer == "cancel":
            return False
        if answer == "save":
            self.lines.save_edit()
        else:
            self.lines.cancel_edit()
        return True

    def _guarded(self, fn) -> None:
        """Run a listening shortcut only when a class with lines is open and nobody is typing."""
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit)) or self.lines.is_editing():
            return
        if self.record is None or self.worker is not None or not self.record.segments:
            return
        fn()

    # ================= library =================
    def library_dir(self) -> Path:
        return Path(self.settings.library_dir)

    def refresh_library(self, select_id: str | None = None) -> None:
        self.sidebar.set_records(store.list_library(self.library_dir()))
        if select_id:
            self.open_class(select_id)

    def open_class(self, class_id: str) -> None:
        if self.worker is not None or not self._settle_edit():
            if self.record is not None:
                self.sidebar.select_class(self.record.class_id)
            return
        try:
            rec = store.load_record(store.class_dir(self.library_dir(), class_id))
        except (OSError, ValueError) as e:
            self._alert("Could not open class", str(e))
            return
        self.show_record(rec, self.library_dir())

    def open_hit(self, class_id: str, seg_id: int) -> None:
        if self.record is None or self.record.class_id != class_id:
            self.open_class(class_id)
        if self.record is None or self.record.class_id != class_id or seg_id < 0:
            return
        seg = self._seg(seg_id)
        if seg is not None:
            self.current_id = seg_id
            self.lines.set_playing(seg_id)
            self.lines.scroll_to(seg_id)
            self.playback.seek_ms(int(seg.start * 1000))

    def show_record(self, rec: store.ClassRecord, library: Path | None = None) -> None:
        self.record = rec
        if library is not None:
            self.record_lib = Path(library)
        self.current_id = None
        self.title.setText(rec.title or rec.class_id)
        audio_ok = Path(rec.audio_path).is_file()
        self.banner.setVisible(not audio_ok)
        self.playback.set_segments(rec.segments)
        self.playback.set_source(rec.audio_path if audio_ok else None)
        self.bar.set_controls_enabled(audio_ok)
        self.bar.set_position(0, int(rec.duration_s * 1000))
        self.lines.set_editable(True)
        self.lines.set_segments(rec.segments)
        self.stack.setCurrentWidget(self.lines)
        self.sidebar.select_class(rec.class_id)
        self._set_record_actions(True)
        self._refresh_counts()
        self.lines.setFocus()  # so Space and the arrows work straight away

    def _refresh_counts(self) -> None:
        rec = self.record
        if rec is None:
            return
        flagged = flags.flagged_ids(rec.segments)
        self.meta.setText(f"{rec.date} · {store.fmt_clock(rec.duration_s)} · {len(rec.segments)} lines · "
                          f"{len(flagged)} to check")
        self.next_flag_btn.setEnabled(bool(flagged))
        starts = [s.start for s in rec.segments if s.id in set(flagged)]
        self.bar.set_flags(starts, rec.duration_s)

    def _set_record_actions(self, on: bool) -> None:
        for w in (self.export_btn, self.more_btn, self.next_flag_btn):
            w.setEnabled(on)

    def _show_welcome(self, heading: str = "Class Notes") -> None:
        self.title.setText(heading)
        self.meta.setText("")
        self.stack.setCurrentWidget(self.welcome)
        self._set_record_actions(False)
        self.bar.set_controls_enabled(False)

    def _seg(self, seg_id: int) -> store.Segment | None:
        segs = self.live_segments if self.worker is not None else (self.record.segments if self.record else [])
        return next((s for s in segs if s.id == seg_id), None)

    # ================= playback =================
    def _line_clicked(self, seg_id: int) -> None:
        self.current_id = seg_id
        self.lines.set_playing(seg_id)
        self.lines.scroll_to(seg_id)
        self.playback.play_segment(seg_id)

    def _line_changed(self, seg_id) -> None:
        self.current_id = seg_id
        self.lines.set_playing(seg_id)

    def _position(self, ms: int) -> None:
        if self.record is not None:
            self.bar.set_position(ms, int(self.record.duration_s * 1000))

    def set_rate(self, rate: float) -> None:
        self.settings.playback_rate = rate
        self.playback.set_rate(rate)
        self.bar.set_rate(rate)
        self._persist()

    def set_stop_after(self, on: bool) -> None:
        self.settings.stop_after_line = on
        self.playback.set_stop_after_line(on)
        self.bar.set_stop_after(on)
        self._persist()

    def set_output(self, device_id: str) -> None:
        self.settings.audio_output = device_id
        self.playback.set_output(device_id)
        self._persist()

    def next_flagged(self) -> None:
        if self.record is None:
            return
        seg_id = flags.next_flagged(self.record.segments, self.current_id)
        seg = self._seg(seg_id) if seg_id is not None else None
        if seg is not None:
            self.current_id = seg_id
            self.lines.set_playing(seg_id)
            self.lines.scroll_to(seg_id)
            self.playback.seek_ms(int(seg.start * 1000))

    # ================= editing =================
    def edit_playing_line(self) -> None:
        target = self.current_id
        if target is None and self.record and self.record.segments:
            target = self.record.segments[0].id
        if target is not None:
            self.lines.scroll_to(target)
            self.lines.start_edit(target)

    def _edit_started(self, _seg_id: int) -> None:
        self._resume_after_edit = self.playback.is_playing()
        self.playback.pause()

    def _edit_saved(self, seg_id: int, text) -> None:
        self.apply_edit(seg_id, text)
        self._resume()

    def _resume(self) -> None:
        if self._resume_after_edit:
            self._resume_after_edit = False
            self.playback.play()

    def apply_edit(self, seg_id: int, text: str | None) -> None:
        seg = self._seg(seg_id)
        if seg is None or self.record is None:
            return
        seg.text_edited = text
        self._save_current()
        self.lines.update_segment(seg_id)
        self.sidebar.update_record(self.record)
        self._refresh_counts()

    def mark_checked(self, seg_id: int) -> None:
        seg = self._seg(seg_id)
        if seg is None or self.record is None:
            return
        seg.checked = True
        self._save_current()
        self.sidebar.update_record(self.record)
        self.lines.update_segment(seg_id)
        self._refresh_counts()

    def _save_current(self) -> bool:
        """Save the open class into the library it was opened from (not today's setting)."""
        try:
            store.save_record(self.record, self.record_lib or self.library_dir())
            return True
        except OSError as e:
            self._alert("Could not save", str(e))
            return False

    def _alert(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    def locate_audio(self) -> None:
        if self.record is None:
            return
        if not self._settle_edit():
            return
        f, _ = QFileDialog.getOpenFileName(self, "Locate the class recording", "", AUDIO_FILTER)
        if f:
            self.record.audio_path = str(Path(f).resolve())
            self._save_current()
            self.show_record(self.record)

    # ================= processing =================
    def new_class(self) -> None:
        if not self._settle_edit():
            return
        dlg = NewClassDialog(self)
        if dlg.exec():
            path, day, title = dlg.values()
            self._start(path, day, title or Path(path).stem, None)

    def reprocess(self) -> None:
        rec = self.record
        if rec is None or not self._settle_edit():
            return
        if not Path(rec.audio_path).is_file():
            QMessageBox.information(self, "Recording missing", "Locate the recording first.")
            return
        ok = QMessageBox.question(
            self, "Re-process class",
            "Run this recording through the models again?\n\nThe current notes (including your "
            "corrections) are kept as a backup file in the class folder.")
        if ok == QMessageBox.Yes:
            self._start(rec.audio_path, rec.date, rec.title, rec.class_id)

    def _start(self, path: str, day: str, title: str, class_id: str | None) -> None:
        self.playback.pause()
        self.playback.set_source(None)
        self.record = None
        self._reprocess_id = class_id
        self.live_segments = []
        self.current_id = None
        self.title.setText(title)
        self.meta.setText(f"{day} · processing…")
        self.banner.hide()
        self._set_record_actions(False)
        self.bar.set_controls_enabled(False)
        self.sidebar.setEnabled(False)
        self.proc_panel.show()
        self.cancel_btn.setEnabled(True)
        self.proc_bar.setValue(0)
        self.proc_status.setText("Starting…")
        self.lines.set_segments([])
        self.lines.set_editable(False)  # lines being made can't be edited yet
        self.stack.setCurrentWidget(self.lines)

        self.worker = ProcessWorker(path, title, day, self.settings, class_id, self)
        self.worker.status.connect(self.proc_status.setText)
        self.worker.progress.connect(self._on_progress)
        self.worker.segment.connect(self._on_segment)
        self.worker.done.connect(self._on_done)
        self.worker.cancelled_run.connect(
            lambda: self._finish("Cancelled. Nothing was saved.", self._reprocess_id))
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, stage: str, frac: float) -> None:
        self.proc_status.setText(f"{stage}… {frac:.0%}")
        self.proc_bar.setValue(int(frac * 1000))

    def _on_segment(self, seg: store.Segment) -> None:
        self.live_segments.append(seg)
        self.lines.append_segment(seg)

    def _on_done(self, rec: store.ClassRecord) -> None:
        self._finish(None)
        self.refresh_library(select_id=rec.class_id)

    def _on_failed(self, msg: str) -> None:
        self._finish("Processing failed.", self._reprocess_id)
        self._alert("Processing failed", msg)

    def _finish(self, message: str | None, reopen_id: str | None = None) -> None:
        if self.worker is not None and hasattr(self.worker, "wait"):
            self.worker.wait()
            self.worker.deleteLater()
        self.worker = None
        self._reprocess_id = None
        self.proc_panel.hide()
        self.sidebar.setEnabled(True)
        self.sidebar.select_class(None)
        if reopen_id:  # a re-process that didn't finish: the class is unchanged, show it again
            self.refresh_library(select_id=reopen_id)
        if self.record is None and message:
            self._show_welcome(message)

    def cancel_processing(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            models.kill_active()  # a first-time model conversion stops at once
            self.cancel_btn.setEnabled(False)
            self.proc_status.setText("Cancelling after the current batch…")

    # ================= misc =================
    def apply_theme(self) -> str:
        """Restyle for the theme setting (and Windows' scheme when following it). Keeps everything
        on screen, including an edit in progress."""
        name = theme.apply(QApplication.instance(), self.settings)
        self.bar.refresh_icons()
        self.lines.restyle()
        return name

    def open_settings(self) -> None:
        if not self._settle_edit():
            return
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            old_lib = self.library_dir()
            dlg.apply(self.settings)
            self._persist()
            if self.library_dir() != old_lib and self.record is not None:
                # The open class belongs to the old library: close it rather than mix the two.
                self.playback.set_source(None)
                self.record, self.record_lib = None, None
                self.banner.hide()
                self._show_welcome()
            self.apply_theme()
            self.refresh_library()

    def _persist(self) -> None:
        if self.persist:
            try:
                self.settings.save()
            except OSError:
                pass

    def export(self, kind: str) -> None:
        rec = self.record
        if rec is None:
            return
        label, ext = next((lab, e) for k, lab, e in export.FORMATS if k == kind)
        start = Path.home() / "Documents" / export.default_name(rec, ext)
        f, _ = QFileDialog.getSaveFileName(self, f"Export {label.lower()}", str(start), f"{label} (*{ext})")
        if not f:
            return
        try:
            export.export(rec, kind, Path(f))
        except OSError as e:
            self._alert("Could not export", str(e))
            return
        self.statusBar().showMessage(f"Saved {Path(f).name}", 8000)

    def open_folder(self) -> None:
        if self.record is not None:
            folder = store.class_dir(self.record_lib or self.library_dir(), self.record.class_id)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def closeEvent(self, event) -> None:
        if not self._settle_edit():
            event.ignore()
            return
        if self.worker is not None and hasattr(self.worker, "wait"):
            ok = QMessageBox.question(self, "Processing", "A recording is still processing. Stop and quit?")
            if ok != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.cancel()
            models.kill_active()
            if not self.worker.wait(30000):
                # Stuck in a download or a GPU call that can't be interrupted. Nothing is saved
                # for a cancelled run, so leave right away instead of crashing on exit.
                self.playback.pause()
                os._exit(0)
        self.playback.pause()
        event.accept()


def _esc(s: str) -> str:
    return escape(s or "")
