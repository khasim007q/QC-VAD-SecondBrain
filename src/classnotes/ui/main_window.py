"""Main window: class library, audio player, segment list, processing panel."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPalette
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QSlider, QSplitter, QStyle,
    QTextBrowser, QVBoxLayout, QWidget,
)

from .. import store
from ..settings import Settings
from .dialogs import AUDIO_FILTER, EditDialog, NewClassDialog, SettingsDialog
from .segment_view import render_segments_html, segment_at
from .worker import ProcessWorker


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings | None = None, persist_settings: bool = True):
        super().__init__()
        self.settings = settings or Settings.load()
        self.persist = persist_settings
        self.record: store.ClassRecord | None = None
        self.worker: ProcessWorker | None = None
        self.live_segments: list[store.Segment] = []
        self.current_id: int | None = None
        self._dragging = False

        self.setWindowTitle("Class Notes")
        self.resize(1180, 760)
        self._build()
        self.refresh_library()

    # ---------- layout ----------
    def _build(self) -> None:
        # Sidebar
        self.library = QListWidget()
        self.library.currentRowChanged.connect(self._open_selected)
        self.library.setStyleSheet(
            "QListWidget::item { padding: 7px 6px; border-bottom: 1px solid palette(midlight); }"
            "QListWidget::item:selected { background: palette(highlight); color: palette(highlighted-text); }")
        self.new_btn = QPushButton("+  New class")
        self.new_btn.setDefault(True)
        self.new_btn.clicked.connect(self.new_class)
        self.settings_btn = QPushButton("Glossary && settings")
        self.settings_btn.clicked.connect(self.open_settings)
        side = QWidget()
        sl = QVBoxLayout(side)
        sl.addWidget(self.new_btn)
        sl.addWidget(self.library, 1)
        sl.addWidget(self.settings_btn)

        # Header + missing-audio banner
        self.header = QLabel()
        self.header.setTextFormat(Qt.RichText)
        self.header.setWordWrap(True)
        self.missing_banner = QFrame()
        self.missing_banner.setStyleSheet(
            "QFrame { background: #fff1e5; border: 1px solid #f0b37e; border-radius: 4px; }"
            "QLabel { color: #7a3e00; border: none; }")
        bl = QHBoxLayout(self.missing_banner)
        self.missing_label = QLabel("The recording for this class was moved or deleted.")
        locate = QPushButton("Locate recording...")
        locate.clicked.connect(self.locate_audio)
        bl.addWidget(self.missing_label, 1)
        bl.addWidget(locate)
        self.missing_banner.hide()

        # Player
        self.player = QMediaPlayer(self)
        self.audio_out = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_out)
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(lambda d: self.slider.setRange(0, d))
        self.player.playbackStateChanged.connect(self._update_play_icon)
        self.play_btn = QPushButton()
        self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.play_btn.clicked.connect(self.toggle_play)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.sliderPressed.connect(lambda: setattr(self, "_dragging", True))
        self.slider.sliderReleased.connect(self._slider_released)
        self.time_label = QLabel("00:00 / 00:00")
        self.follow = QCheckBox("Follow playback")
        self.follow.setChecked(True)
        player_row = QHBoxLayout()
        player_row.addWidget(self.play_btn)
        player_row.addWidget(self.slider, 1)
        player_row.addWidget(self.time_label)
        player_row.addWidget(self.follow)

        # Processing panel
        self.proc_panel = QFrame()
        pl = QHBoxLayout(self.proc_panel)
        pl.setContentsMargins(0, 0, 0, 0)
        self.proc_status = QLabel()
        self.proc_bar = QProgressBar()
        self.proc_bar.setRange(0, 1000)
        self.proc_bar.setTextVisible(False)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_processing)
        pl.addWidget(self.proc_status, 2)
        pl.addWidget(self.proc_bar, 3)
        pl.addWidget(self.cancel_btn)
        self.proc_panel.hide()

        # Segments
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self._on_link)

        # Actions
        self.export_md_btn = QPushButton("Export notes.md")
        self.export_md_btn.clicked.connect(lambda: self.export("md"))
        self.export_srt_btn = QPushButton("Export .srt")
        self.export_srt_btn.clicked.connect(lambda: self.export("srt"))
        self.folder_btn = QPushButton("Open folder")
        self.folder_btn.clicked.connect(self.open_folder)
        self.reprocess_btn = QPushButton("Re-process")
        self.reprocess_btn.clicked.connect(self.reprocess)
        actions = QHBoxLayout()
        for b in (self.export_md_btn, self.export_srt_btn, self.folder_btn):
            actions.addWidget(b)
        actions.addStretch(1)
        actions.addWidget(self.reprocess_btn)

        main = QWidget()
        ml = QVBoxLayout(main)
        ml.addWidget(self.header)
        ml.addWidget(self.missing_banner)
        ml.addLayout(player_row)
        ml.addWidget(self.proc_panel)
        ml.addWidget(self.view, 1)
        ml.addLayout(actions)

        split = QSplitter()
        split.addWidget(side)
        split.addWidget(main)
        split.setStretchFactor(1, 1)
        split.setSizes([260, 920])
        self.setCentralWidget(split)
        self._set_record_actions(False)
        self._show_welcome()

    def _dark(self) -> bool:
        return self.palette().color(QPalette.Window).lightness() < 128

    def _set_record_actions(self, on: bool) -> None:
        for w in (self.export_md_btn, self.export_srt_btn, self.folder_btn, self.reprocess_btn,
                  self.play_btn, self.slider):
            w.setEnabled(on)

    def _show_welcome(self) -> None:
        self.header.setText("<h2>Class Notes</h2>")
        self.view.setHtml(
            "<p>Click <b>+ New class</b> and choose a recording. Urdu is translated to English "
            "line by line, the teacher's English is kept exactly as spoken, and Quran recitation "
            "is marked but not translated.</p><p>Click a time to hear that moment. "
            "Click ✎ to correct a translation (the machine version is always kept).</p>")

    # ---------- library ----------
    def library_dir(self) -> Path:
        return Path(self.settings.library_dir)

    def refresh_library(self, select_id: str | None = None) -> None:
        self.library.blockSignals(True)
        self.library.clear()
        for rec in store.list_library(self.library_dir()):
            label = f"{rec.date}\n{rec.title or rec.class_id}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, rec.class_id)
            self.library.addItem(item)
            if rec.class_id == select_id:
                self.library.setCurrentItem(item)
        self.library.blockSignals(False)
        if select_id:
            self._open_selected(self.library.currentRow())

    def _open_selected(self, row: int) -> None:
        if row < 0:
            return
        class_id = self.library.item(row).data(Qt.UserRole)
        try:
            rec = store.load_record(store.class_dir(self.library_dir(), class_id))
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Could not open class", str(e))
            return
        self.show_record(rec)

    def show_record(self, rec: store.ClassRecord) -> None:
        self.record = rec
        self.current_id = None
        n = len(rec.segments)
        mins = int(rec.duration_s // 60)
        self.header.setText(
            f"<h2 style='margin:0'>{_esc(rec.title or rec.class_id)}</h2>"
            f"<span style='color:gray'>{rec.date} · {mins} min · {n} segments · "
            f"{_esc(Path(rec.audio_path).name)}</span>")
        self.player.stop()
        audio_ok = Path(rec.audio_path).is_file()
        self.missing_banner.setVisible(not audio_ok)
        self.player.setSource(QUrl.fromLocalFile(rec.audio_path) if audio_ok else QUrl())
        self._set_record_actions(True)
        self.play_btn.setEnabled(audio_ok)
        self.slider.setEnabled(audio_ok)
        self._render(keep_scroll=False)

    def _segments(self) -> list[store.Segment]:
        if self.worker is not None:
            return self.live_segments
        return self.record.segments if self.record else []

    def _render(self, keep_scroll: bool = True, stick_bottom: bool = False) -> None:
        sb = self.view.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        pos = sb.value()
        self.view.setHtml(render_segments_html(self._segments(), self.current_id, self._dark()))
        if stick_bottom and at_bottom:
            sb.setValue(sb.maximum())
        elif keep_scroll:
            sb.setValue(pos)

    # ---------- links / playback ----------
    def _on_link(self, url: QUrl) -> None:
        kind, _, value = url.toString().partition(":")
        if not value.isdigit() or self.record is None:
            return
        seg_id = int(value)
        if kind == "seek":
            self.seek_to(seg_id)
        elif kind == "edit":
            self.edit_segment(seg_id)

    def _seg_by_id(self, seg_id: int) -> store.Segment | None:
        return next((s for s in self._segments() if s.id == seg_id), None)

    def seek_to(self, seg_id: int) -> None:
        seg = self._seg_by_id(seg_id)
        if seg is None or self.player.source().isEmpty():
            return
        self.player.setPosition(int(seg.start * 1000))
        self.player.play()

    def toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _update_play_icon(self, state) -> None:
        icon = QStyle.SP_MediaPause if state == QMediaPlayer.PlayingState else QStyle.SP_MediaPlay
        self.play_btn.setIcon(self.style().standardIcon(icon))

    def _slider_released(self) -> None:
        self._dragging = False
        self.player.setPosition(self.slider.value())

    def _position_changed(self, ms: int) -> None:
        if not self._dragging:
            self.slider.setValue(ms)
        self.time_label.setText(
            f"{store.fmt_clock(ms / 1000)} / {store.fmt_clock(self.player.duration() / 1000)}")
        segs = self._segments()
        idx = segment_at(segs, ms / 1000)
        new_id = segs[idx].id if idx is not None else self.current_id
        if new_id != self.current_id:
            self.current_id = new_id
            self._render()
            if self.follow.isChecked() and new_id is not None:
                self.view.scrollToAnchor(f"seg-{new_id}")

    # ---------- editing ----------
    def edit_segment(self, seg_id: int) -> None:
        seg = self._seg_by_id(seg_id)
        if seg is None or seg.lang == "ar" or self.worker is not None:
            return
        dlg = EditDialog(seg, self)
        if dlg.exec():
            seg.text_edited = dlg.edited_text()
            store.save_record(self.record, self.library_dir())
            self._render()

    def locate_audio(self) -> None:
        if self.record is None:
            return
        f, _ = QFileDialog.getOpenFileName(self, "Locate the class recording", "", AUDIO_FILTER)
        if f:
            self.record.audio_path = str(Path(f).resolve())
            store.save_record(self.record, self.library_dir())
            self.show_record(self.record)

    # ---------- processing ----------
    def new_class(self) -> None:
        dlg = NewClassDialog(self)
        if dlg.exec():
            path, day, title = dlg.values()
            self._start(path, day, title or Path(path).stem, None)

    def reprocess(self) -> None:
        rec = self.record
        if rec is None:
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
        self.player.stop()
        self.record = None
        self.live_segments = []
        self.current_id = None
        self.header.setText(f"<h2 style='margin:0'>{_esc(title)}</h2>"
                            f"<span style='color:gray'>{day} · processing…</span>")
        self.missing_banner.hide()
        self._set_record_actions(False)
        self.new_btn.setEnabled(False)
        self.settings_btn.setEnabled(False)
        self.library.setEnabled(False)
        self.proc_panel.show()
        self.cancel_btn.setEnabled(True)
        self.proc_bar.setValue(0)
        self.proc_status.setText("Starting…")
        self.view.setHtml("<p style='color:gray'>Segments appear here as they are processed.</p>")

        self.worker = ProcessWorker(path, title, day, self.settings, class_id, self)
        self.worker.status.connect(self.proc_status.setText)
        self.worker.progress.connect(self._on_progress)
        self.worker.segment.connect(self._on_segment)
        self.worker.done.connect(self._on_done)
        self.worker.cancelled_run.connect(lambda: self._finish("Cancelled. Nothing was saved."))
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, stage: str, frac: float) -> None:
        self.proc_status.setText(f"{stage}… {frac:.0%}")
        self.proc_bar.setValue(int(frac * 1000))

    def _on_segment(self, seg: store.Segment) -> None:
        self.live_segments.append(seg)
        self._render(stick_bottom=True)

    def _on_done(self, rec: store.ClassRecord) -> None:
        self._finish(None)
        self.refresh_library(select_id=rec.class_id)

    def _on_failed(self, msg: str) -> None:
        self._finish(None)
        QMessageBox.critical(self, "Processing failed", msg)

    def _finish(self, message: str | None) -> None:
        if self.worker is not None:
            self.worker.wait()
            self.worker.deleteLater()
        self.worker = None
        self.proc_panel.hide()
        self.new_btn.setEnabled(True)
        self.settings_btn.setEnabled(True)
        self.library.setEnabled(True)
        if message:
            self._show_welcome()
            self.header.setText(f"<h2>{_esc(message)}</h2>")

    def cancel_processing(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.proc_status.setText("Cancelling after the current phrase…")

    # ---------- misc ----------
    def open_settings(self) -> None:
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            dlg.apply(self.settings)
            if self.persist:
                self.settings.save()
            self.refresh_library()

    def export(self, kind: str) -> None:
        rec = self.record
        if rec is None:
            return
        if kind == "md":
            name, text, filt = f"{rec.class_id}-notes.md", store.render_notes_md(rec), "Markdown (*.md)"
        else:
            name, text, filt = f"{rec.class_id}.srt", store.render_srt(rec), "Subtitles (*.srt)"
        f, _ = QFileDialog.getSaveFileName(self, "Export", str(Path.home() / "Documents" / name), filt)
        if f:
            Path(f).write_text(text, "utf-8")

    def open_folder(self) -> None:
        if self.record is not None:
            folder = store.class_dir(self.library_dir(), self.record.class_id)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def closeEvent(self, event) -> None:
        if self.worker is not None:
            ok = QMessageBox.question(self, "Processing", "A recording is still processing. Stop and quit?")
            if ok != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.cancel()
            self.worker.wait(30000)
        self.player.stop()
        event.accept()


def _esc(s: str) -> str:
    from html import escape

    return escape(s or "")
