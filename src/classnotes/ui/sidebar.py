"""Sidebar: the app name, search across all classes, the class list, and the main actions."""

from __future__ import annotations

from html import escape
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from ..search import SearchIndex
from ..store import ClassRecord, fmt_clock

SEARCH_DELAY_MS = 150


class Sidebar(QWidget):
    class_selected = Signal(str)
    hit_selected = Signal(str, int)  # class id, segment id (-1: the title matched)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(280)
        self._index = SearchIndex([])

        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QPixmap(str(Path(__file__).with_name("icon.png"))).scaled(
            28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        name = QLabel("Class Notes")
        name.setObjectName("Brand")
        brand.addWidget(logo)
        brand.addWidget(name, 1)

        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("Search all classes   Ctrl+K")
        self.search.setClearButtonEnabled(True)
        self.search.setFocusPolicy(Qt.ClickFocus)  # never grabs focus on its own (Ctrl+K or a click)
        self.search.installEventFilter(self)
        self._timer = QTimer(self, singleShot=True, interval=SEARCH_DELAY_MS, timeout=self.flush_search)
        self.search.textChanged.connect(lambda _t: self._timer.start())

        self.label = QLabel("Classes")
        self.label.setObjectName("SectionLabel")
        self.classes = QListWidget()
        self.classes.setObjectName("Classes")
        self.classes.setWordWrap(True)
        self.classes.setTextElideMode(Qt.ElideNone)
        self.classes.itemClicked.connect(self._class_clicked)
        self.classes.itemActivated.connect(self._class_clicked)
        self.results = QListWidget()
        self.results.setObjectName("Results")
        self.results.itemClicked.connect(self._hit_clicked)
        self.results.itemActivated.connect(self._hit_clicked)
        self.results.hide()

        self.add_button = QPushButton("Add a class")
        self.add_button.setProperty("kind", "primary")
        self.settings_button = QPushButton("Glossary and settings")
        self.settings_button.setProperty("kind", "secondary")
        for b in (self.add_button, self.settings_button):
            b.setCursor(Qt.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 24, 16, 16)
        lay.setSpacing(12)
        lay.addLayout(brand)
        lay.addWidget(self.search)
        lay.addWidget(self.label)
        lay.addWidget(self.classes, 1)
        lay.addWidget(self.results, 1)
        lay.addWidget(self.add_button)
        lay.addWidget(self.settings_button)

    # ----- classes -----
    def set_records(self, records: list[ClassRecord]) -> None:
        current = self.classes.currentItem().data(Qt.UserRole) if self.classes.currentItem() else None
        self._index = SearchIndex(records)
        self.classes.blockSignals(True)
        self.classes.clear()
        for rec in records:
            item = QListWidgetItem(f"{rec.title or rec.class_id}\n{rec.date} · {fmt_clock(rec.duration_s)}")
            item.setData(Qt.UserRole, rec.class_id)
            item.setSizeHint(QSize(0, 64))  # two lines; Qt ignores stylesheet padding when sizing items
            self.classes.addItem(item)
        self.classes.blockSignals(False)
        self.select_class(current)
        if self.search.text():
            self.flush_search()

    def select_class(self, class_id: str | None) -> None:
        self.classes.blockSignals(True)
        self.classes.setCurrentRow(-1)
        for i in range(self.classes.count()):
            if self.classes.item(i).data(Qt.UserRole) == class_id:
                self.classes.setCurrentRow(i)
        self.classes.blockSignals(False)

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _class_clicked(self, item: QListWidgetItem) -> None:
        self.class_selected.emit(item.data(Qt.UserRole))

    # ----- search -----
    def flush_search(self) -> None:
        self._timer.stop()
        hits = self._index.search(self.search.text())
        searching = sum(ch.isalnum() for ch in self.search.text()) >= 2
        self.classes.setVisible(not searching)
        self.results.setVisible(searching)
        self.label.setText("Search results" if searching else "Classes")
        if not searching:
            return
        self.results.clear()
        if not hits:
            item = QListWidgetItem("No lines match.")
            item.setFlags(Qt.NoItemFlags)
            self.results.addItem(item)
            return
        last_class = None
        for h in hits:
            if h.class_id != last_class:
                head = QListWidgetItem(h.title)
                head.setFlags(Qt.NoItemFlags)
                f = head.font()
                f.setWeight(f.Weight.DemiBold)
                head.setFont(f)
                self.results.addItem(head)
                last_class = h.class_id
            when = "title" if h.seg_id < 0 else fmt_clock(h.start)
            snippet = (escape(h.snippet[:h.match_start]) + "<b>" + escape(h.snippet[h.match_start:h.match_end])
                       + "</b>" + escape(h.snippet[h.match_end:]))
            item = QListWidgetItem()
            item.setData(Qt.UserRole, (h.class_id, h.seg_id))
            label = QLabel(f"<span style='font-family:monospace'>{when}</span> · {snippet}")
            label.setWordWrap(True)
            label.setTextFormat(Qt.RichText)
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            label.setContentsMargins(4, 2, 4, 2)
            item.setSizeHint(QSize(240, label.heightForWidth(232) + 12))
            self.results.addItem(item)
            self.results.setItemWidget(item, label)

    def _hit_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if data:
            self.hit_selected.emit(*data)

    def eventFilter(self, obj, event):
        if obj is self.search and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.search.clear()
            self.flush_search()
            return True
        return super().eventFilter(obj, event)
