"""The list of lines: one small widget per line in a scroll area. The playing line is boxed (a
property, so nothing is rebuilt), the English can be edited in place, and lines to check say why."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from ..flags import flag_reason
from ..store import Segment, display_text, fmt_clock
from . import theme

LANG_NAME = {"ur": "Urdu", "en": "English", "ar": "Recitation"}
FIRST_LINES = 30  # built at once when a class opens; the rest follow in batches
BATCH_LINES = 40
BATCH_DELAY_MS = 15


def _link(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setProperty("kind", "link")
    b.setFlat(True)
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.NoFocus)
    return b



class Editor(QPlainTextEdit):
    """The in-place English editor: Enter saves, Shift+Enter starts a new line, Esc cancels."""

    save = Signal()
    cancel = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Editor")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTabChangesFocus(True)
        self.document().contentsChanged.connect(self._fit)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if e.oldSize().width() != e.size().width():
            self._fit()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
            self.save.emit()
            return
        if e.key() == Qt.Key_Escape:
            self.cancel.emit()
            return
        super().keyPressEvent(e)

    def _fit(self) -> None:
        lines = max(2, int(self.document().size().height()))
        self.setFixedHeight(min(400, lines * self.fontMetrics().lineSpacing() + 28))


class LineWidget(QFrame):
    def __init__(self, seg: Segment, owner: "LineList"):
        super().__init__()
        self.seg, self.owner = seg, owner
        self.setObjectName("Line")
        self.setProperty("playing", False)
        self._hover = False
        self.setProperty("flagged", False)
        self.setCursor(Qt.PointingHandCursor)

        self.time = QLabel(fmt_clock(seg.start))
        self.time.setObjectName("Time")
        self.lang = QLabel(LANG_NAME.get(seg.lang, seg.lang))
        self.lang.setObjectName("Lang")
        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(self.time)
        left.addWidget(self.lang)
        left.addStretch(1)

        self.english = QLabel()
        self.english.setObjectName("English")
        self.english.setWordWrap(True)
        self.english.setTextInteractionFlags(Qt.NoTextInteraction)
        self.source = QLabel(seg.source)
        self.source.setObjectName("Arabic" if seg.lang == "ar" else "Urdu")
        self.source.setWordWrap(True)
        self.source.setLayoutDirection(Qt.RightToLeft)
        self.source.setAlignment(Qt.AlignRight | Qt.AlignTop)
        self.slot = QVBoxLayout()  # phase 3 puts the matched Quran verse here

        self.flag_label = QLabel()
        self.flag_label.setObjectName("FlagLabel")
        self.tag = QLabel()
        self.tag.setObjectName("Tag")
        self.edit_btn = _link("Edit translation")
        self.revert_btn = _link("Revert to machine")
        self.looks_fine_btn = _link("Looks fine")
        self.edit_btn.clicked.connect(lambda: owner.start_edit(seg.id))
        self.revert_btn.clicked.connect(lambda: owner.edit_saved.emit(seg.id, None))
        self.looks_fine_btn.clicked.connect(lambda: owner.marked_checked.emit(seg.id))
        tools = QHBoxLayout()
        tools.setSpacing(16)
        for w in (self.flag_label, self.tag, self.edit_btn, self.revert_btn, self.looks_fine_btn):
            tools.addWidget(w)
        tools.addStretch(1)
        self.tools = tools

        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        self.body.addWidget(self.english)
        self.body.addWidget(self.source)
        self.body.addLayout(self.slot)
        self.body.addLayout(tools)

        grid = QGridLayout(self)
        grid.setContentsMargins(16, 16, 16, 16)
        grid.setHorizontalSpacing(16)
        grid.setColumnMinimumWidth(0, 72)
        grid.addLayout(left, 0, 0)
        grid.addLayout(self.body, 0, 1)
        grid.setColumnStretch(1, 1)
        self.refresh()

    def refresh(self) -> None:
        seg = self.seg
        recitation = seg.lang == "ar"
        self.english.setText(display_text(seg))
        self.english.setVisible(not recitation and bool(display_text(seg)))
        self.source.setText(seg.source)
        self.source.setVisible(seg.lang != "en" and bool(seg.source))
        reason = flag_reason(seg)
        self.flag_label.setText(f"Check: {reason.lower()}" if reason else "")
        self.flag_label.setVisible(bool(reason))
        self.tag.setText("Recitation, not translated" if recitation else ("edited" if seg.text_edited else ""))
        self.tag.setVisible(bool(self.tag.text()))
        editable = self.owner.editable and self.owner._editing != seg.id
        self.edit_btn.setVisible(editable and not recitation)
        self.revert_btn.setVisible(editable and bool(seg.text_edited))
        self.looks_fine_btn.setVisible(editable and bool(reason))
        self.setProperty("flagged", bool(reason))

    def set_playing(self, on: bool) -> None:
        if self.property("playing") != on:
            self.setProperty("playing", on)
            t = theme.current()["tokens"]
            colour = t["accent"] if on else t["muted"]
            self.time.setText(f"<span style='color:{colour}'>{fmt_clock(self.seg.start)}</span>")
            self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, e):
        playing = self.property("playing")
        if playing or self._hover:
            t = theme.current()["tokens"]
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            p.setBrush(QColor(t["panel"] if playing else t["hover"]))
            p.setPen(QPen(QColor(t["line_strong"]), 1) if playing else Qt.NoPen)
            p.drawRoundedRect(r, 12, 12)
            p.end()
        super().paintEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not self.owner.is_editing():
            self.owner.seek_requested.emit(self.seg.id)
        super().mousePressEvent(e)


class LineList(QScrollArea):
    seek_requested = Signal(int)
    edit_saved = Signal(int, object)  # seg id, new English or None (back to the machine text)
    edit_started = Signal(int)
    edit_cancelled = Signal(int)
    marked_checked = Signal(int)
    following_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LineList")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lines: dict[int, LineWidget] = {}
        self.segments: list[Segment] = []
        self.playing: int | None = None
        self.following = True
        self.editor: Editor | None = None
        self._editing: int | None = None
        self._auto = False  # True while the list itself scrolls
        self.editable = True
        self._pending: list[Segment] = []  # lines not built yet
        self._batch_timer = QTimer(self, singleShot=True, interval=BATCH_DELAY_MS, timeout=self._build_batch)

        self.host = QWidget()
        self.host.setObjectName("LineHost")
        self.layout_ = QVBoxLayout(self.host)
        self.layout_.setContentsMargins(32, 16, 32, 48)
        self.layout_.setSpacing(4)
        self.empty_label = QLabel("No speech found.")
        self.empty_label.setObjectName("Empty")
        self.empty_label.hide()
        self.setWidget(self.host)

        self.back_btn = QPushButton("Back to the playing line", self.viewport())
        self.back_btn.setProperty("kind", "secondary")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self._resume_following)
        self.back_btn.hide()
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    # ----- content -----
    def set_segments(self, segments: list[Segment]) -> None:
        self._end_edit()
        self.setUpdatesEnabled(False)
        while self.layout_.count():
            item = self.layout_.takeAt(0)
            if item.widget() and item.widget() is not self.empty_label:
                item.widget().deleteLater()
        self.lines, self.segments, self.playing = {}, list(segments), None
        self._batch_timer.stop()
        self.layout_.addWidget(self.empty_label)
        self.empty_label.setVisible(not self.segments)
        self.layout_.addStretch(1)
        self._pending = list(self.segments)
        self._build(FIRST_LINES)
        self.setUpdatesEnabled(True)
        self._set_following(True)

    def _add_line(self, seg: Segment) -> None:
        w = LineWidget(seg, self)
        w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.lines[seg.id] = w
        self.layout_.insertWidget(self.layout_.indexOf(self.empty_label), w)

    def _build(self, n: int) -> None:
        for seg in self._pending[:n]:
            self._add_line(seg)
        del self._pending[:n]
        if self._pending:
            self._batch_timer.start()

    def _build_batch(self) -> None:
        self._build(BATCH_LINES)

    def _ensure_built(self, seg_id: int | None) -> None:
        """Build every line up to `seg_id` now (e.g. jumping far into a class just opened)."""
        if seg_id is None or seg_id in self.lines or not self._pending:
            return
        ids = [s.id for s in self._pending]
        if seg_id in ids:
            self._build(ids.index(seg_id) + 1)

    def set_editable(self, on: bool) -> None:
        """Off while a class is being processed: nothing can be edited or marked yet."""
        self.editable = on
        for w in self.lines.values():
            w.refresh()

    def append_segment(self, seg: Segment) -> None:
        """Add one line at the end (while a class is being processed) without rebuilding."""
        self.segments.append(seg)
        self._add_line(seg)
        self.empty_label.hide()

    def update_segment(self, seg_id: int) -> None:
        w = self.lines.get(seg_id)
        if w is not None:
            w.refresh()

    # ----- playing line and following -----
    def set_playing(self, seg_id: int | None) -> None:
        self._ensure_built(seg_id)
        if self.playing in self.lines:
            self.lines[self.playing].set_playing(False)
        self.playing = seg_id
        if seg_id in self.lines:
            self.lines[seg_id].set_playing(True)
            if self.following:
                self._show(seg_id)

    def scroll_to(self, seg_id: int) -> None:
        self._ensure_built(seg_id)
        self._set_following(True)
        self._show(seg_id)

    def _show(self, seg_id: int) -> None:
        self._show_now(seg_id)
        # Right after opening a class the layout isn't measured yet: try again once it is.
        QTimer.singleShot(0, lambda: self.following and self.playing == seg_id and self._show_now(seg_id))

    def _show_now(self, seg_id: int) -> None:
        w = self.lines.get(seg_id)
        if w is None:
            return
        self._auto = True
        bar = self.verticalScrollBar()
        target = w.y() + w.height() // 2 - self.viewport().height() // 2
        if not (bar.value() <= w.y() and w.y() + w.height() <= bar.value() + self.viewport().height() - 80):
            bar.setValue(max(0, target))
        self._auto = False

    def _on_scroll(self, _value: int) -> None:
        if not self._auto and self.playing is not None:
            self._set_following(False)

    def _resume_following(self) -> None:
        self._set_following(True)
        if self.playing is not None:
            self._show(self.playing)

    def _set_following(self, on: bool) -> None:
        changed = on != self.following
        self.following = on
        self.back_btn.setVisible(not on)
        if not on:
            self._place_back_button()
        if changed:
            self.following_changed.emit(on)

    def _place_back_button(self) -> None:
        self.back_btn.adjustSize()
        vp = self.viewport()
        self.back_btn.move(vp.width() - self.back_btn.width() - 24, vp.height() - self.back_btn.height() - 24)
        self.back_btn.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.back_btn.isVisible():
            self._place_back_button()

    # ----- editing -----
    def is_editing(self) -> bool:
        return self._editing is not None

    def edit_text(self) -> str | None:
        return self.editor.toPlainText() if self.editor is not None else None

    def start_edit(self, seg_id: int) -> bool:
        self._ensure_built(seg_id)
        w = self.lines.get(seg_id)
        if w is None or w.seg.lang == "ar" or self.is_editing() or not self.editable:
            return False
        self._editing = seg_id
        self.editor = Editor(w)
        self.editor.setPlainText(display_text(w.seg))
        self.editor.save.connect(self._save)
        self.editor.cancel.connect(self._cancel)
        self._hint = QLabel("Enter saves · Shift+Enter new line · Esc cancels · the machine version is kept")
        self._hint.setObjectName("Hint")
        w.english.hide()
        w.body.insertWidget(0, self.editor)
        w.body.insertWidget(1, self._hint)
        w.refresh()  # hides this line's links while it is being edited
        self.editor._fit()
        QTimer.singleShot(0, lambda ed=self.editor: ed is self.editor and ed._fit())  # once laid out
        self.editor.setFocus()
        self.editor.moveCursor(self.editor.textCursor().MoveOperation.End)
        self.edit_started.emit(seg_id)
        return True

    def save_edit(self) -> None:
        if self.is_editing():
            self._save()

    def cancel_edit(self) -> None:
        if self.is_editing():
            self._cancel()

    def restyle(self) -> None:
        """After a theme change: recolour the painted highlight and the playing line's time."""
        w = self.lines.get(self.playing)
        if w is not None:
            w.setProperty("playing", False)
            w.set_playing(True)
        self.viewport().update()

    def _save(self) -> None:
        seg_id, text = self._editing, self.edit_text().strip()
        w = self.lines[seg_id]
        value = None if (not text or text == w.seg.text.strip()) else text
        self._end_edit()
        self.edit_saved.emit(seg_id, value)

    def _cancel(self) -> None:
        seg_id = self._editing
        self._end_edit()
        self.edit_cancelled.emit(seg_id)

    def _end_edit(self) -> None:
        if self._editing is None:
            return
        w = self.lines.get(self._editing)
        self._editing = None
        if self.editor is not None:
            self.editor.deleteLater()
            self._hint.deleteLater()
            self.editor = None
        if w is not None:
            w.refresh()
        self.setFocus()  # back to listening: shortcuts work again
