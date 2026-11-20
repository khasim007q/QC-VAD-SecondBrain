"""New class and settings dialogs."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ..settings import Settings

AUDIO_FILTER = "Audio/video (*.mp3 *.m4a *.wav *.aac *.ogg *.opus *.flac *.wma *.mp4 *.webm *.mkv);;All files (*)"


def _browse_row(edit: QLineEdit, button_text: str, on_click) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(edit, 1)
    b = QPushButton(button_text)
    b.clicked.connect(on_click)
    lay.addWidget(b)
    return w


class NewClassDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New class")
        self.setMinimumWidth(520)
        self.path = QLineEdit()
        self.path.setPlaceholderText("Choose the class recording...")
        self.path.setReadOnly(True)
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.title = QLineEdit()
        self.title.setPlaceholderText("e.g. Surah Al-Kahf, ayat 1-10")

        form = QFormLayout()
        form.addRow("Recording", _browse_row(self.path, "Browse...", self._browse))
        form.addRow("Class date", self.date)
        form.addRow("Title", self.title)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Process")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        note = QLabel("Processing runs on this PC. Nothing is uploaded.")
        note.setStyleSheet("color: gray;")
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(note)
        lay.addWidget(self.buttons)

    def _browse(self):
        f, _ = QFileDialog.getOpenFileName(self, "Choose class recording", "", AUDIO_FILTER)
        if not f:
            return
        self.path.setText(f)
        d = date.fromtimestamp(Path(f).stat().st_mtime)
        self.date.setDate(QDate(d.year, d.month, d.day))
        if not self.title.text():
            self.title.setText(Path(f).stem)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(True)

    def values(self) -> tuple[str, str, str]:
        return self.path.text(), self.date.date().toString("yyyy-MM-dd"), self.title.text().strip()


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Glossary & settings")
        self.setMinimumWidth(560)
        s = settings
        self.glossary = QPlainTextEdit(s.glossary)
        self.glossary.setMinimumHeight(90)
        self.terms = QPlainTextEdit(s.terms)
        self.terms.setMinimumHeight(140)
        self.device = QComboBox()
        self.device.addItems(["auto", "cuda", "cpu"])
        self.device.setCurrentText(s.device)
        self.whisper = QComboBox()
        for name, label in (("large-v3-turbo", "Whisper large-v3-turbo (fast, default)"),
                            ("large-v3", "Whisper large-v3 (about 2-3x slower)")):
            self.whisper.addItem(label, name)
        self.whisper.setCurrentIndex(max(0, self.whisper.findData(s.whisper_model)))
        self.theme = QComboBox()
        for value, label in (("system", "Follow Windows"), ("light", "Light"), ("dark", "Dark")):
            self.theme.addItem(label, value)
        self.theme.setCurrentIndex(max(0, self.theme.findData(s.theme)))
        self.library = QLineEdit(s.library_dir)
        self.min_silence = QSpinBox(minimum=100, maximum=3000, singleStep=100, value=s.min_silence_ms)
        self.max_speech = self._dbl(s.max_speech_s, 5, 30, 1)
        self.min_conf = self._dbl(s.min_conf, 0.5, 0.95, 0.05)
        self.min_dur = self._dbl(s.min_dur_s, 0.5, 5, 0.5)
        self.merge_gap = self._dbl(s.merge_gap_s, 0, 5, 0.5)
        self.merge_max = self._dbl(s.merge_max_s, 5, 29, 1)

        form = QFormLayout()
        hint = QLabel("Words Whisper should expect: surah names, Islamic terms, the teacher's common phrases.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        form.addRow("Glossary", self.glossary)
        form.addRow("", hint)
        form.addRow("Replace before\ntranslating", self.terms)
        terms_hint = QLabel("One per line: urdu = replacement. Fixes words Whisper mis-spells or "
                            "NLLB mistranslates. The Urdu shown in the notes is not changed.")
        terms_hint.setWordWrap(True)
        terms_hint.setStyleSheet("color: gray;")
        form.addRow("", terms_hint)
        form.addRow("Library folder", _browse_row(self.library, "Browse...", self._browse))
        form.addRow("Theme", self.theme)
        form.addRow("Speech model", self.whisper)
        form.addRow("Device", self.device)
        form.addRow("Min. silence between phrases (ms)", self.min_silence)
        form.addRow("Max. phrase length (s)", self.max_speech)
        form.addRow("Language confidence needed", self.min_conf)
        form.addRow("Shorter phrases count as Urdu (s)", self.min_dur)
        form.addRow("Join phrases with gaps under (s)", self.merge_gap)
        form.addRow("Max. joined length (s)", self.merge_max)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    @staticmethod
    def _dbl(v, lo, hi, step):
        w = QDoubleSpinBox(minimum=lo, maximum=hi, singleStep=step, value=v)
        w.setDecimals(2)
        return w

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Library folder", self.library.text())
        if d:
            self.library.setText(d)

    def apply(self, s: Settings) -> None:
        s.glossary = self.glossary.toPlainText().strip()
        s.terms = self.terms.toPlainText().strip() + "\n"
        s.device = self.device.currentText()
        s.whisper_model = self.whisper.currentData()
        s.theme = self.theme.currentData()
        s.library_dir = self.library.text().strip() or s.library_dir
        s.min_silence_ms = self.min_silence.value()
        s.max_speech_s = self.max_speech.value()
        s.min_conf = self.min_conf.value()
        s.min_dur_s = self.min_dur.value()
        s.merge_gap_s = self.merge_gap.value()
        s.merge_max_s = self.merge_max.value()
