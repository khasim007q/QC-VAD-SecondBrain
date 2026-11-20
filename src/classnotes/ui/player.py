"""Playback: a controller around QMediaPlayer (speed, stop after this line, sound output) and the
player bar at the bottom of the window."""

from __future__ import annotations

from bisect import bisect_right
from typing import Callable

from PySide6.QtCore import QObject, QPointF, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget,
)

from ..store import Segment, fmt_clock
from . import theme

RATES = (0.75, 1.0, 1.25, 1.5)
RESTART_AFTER_S = 1.0  # "previous" more than this far into a line restarts it


# ---------- pure helpers ----------
def segment_at(segments: list[Segment], t: float) -> int | None:
    """Index of the segment playing at time t (seconds), or None in a gap."""
    i = bisect_right([s.start for s in segments], t) - 1
    if i >= 0 and t <= segments[i].end:
        return i
    return None


def step_line(segments: list[Segment], t: float, delta: int) -> int | None:
    """Index of the line to jump to from time t: delta -1 = previous, +1 = next."""
    if not segments:
        return None
    i = bisect_right([s.start for s in segments], t) - 1  # last line starting at or before t
    if delta > 0:
        return i + 1 if i + 1 < len(segments) else None
    if i < 0:
        return 0
    inside = segment_at(segments, t) == i
    if not inside or t - segments[i].start > RESTART_AFTER_S:
        return i  # in the gap after line i, or well into it: back to its start
    return max(0, i - 1)


def step_rate(rate: float, delta: int) -> float:
    """The next speed up (delta > 0) or down from `rate`, clamped to RATES."""
    if delta > 0:
        up = [r for r in RATES if r > rate + 1e-9]
        return up[0] if up else RATES[-1]
    down = [r for r in RATES if r < rate - 1e-9]
    return down[-1] if down else RATES[0]


def pick_output(devices: list[tuple[str, str]], wanted_id: str, default_id: str) -> tuple[str, bool]:
    """(device id to use, fell back?) — "" means follow the Windows default."""
    if wanted_id and any(d == wanted_id for d, _ in devices):
        return wanted_id, False
    return default_id, bool(wanted_id)


# ---------- controller ----------
def _device_id(dev) -> str:
    return bytes(dev.id().data()).decode("utf-8", "replace")


class Playback(QObject):
    position = Signal(int)
    line_changed = Signal(object)  # segment id
    playing_changed = Signal(bool)
    status = Signal(str)
    error = Signal(str)

    def __init__(self, parent=None, player=None,
                 devices: Callable[[], tuple[list[tuple[str, str]], str]] | None = None,
                 set_device: Callable[[str], None] | None = None):
        super().__init__(parent)
        if player is None:  # production: the real player, output and device list
            player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            player.setAudioOutput(self._audio)
            self._media = QMediaDevices(self)
            self._media.audioOutputsChanged.connect(self.devices_changed)
            devices = devices or self._system_devices
            set_device = set_device or self._set_system_device
            # Some Windows drivers don't report a default-device switch: check every 2 s too.
            self._poll = QTimer(self, interval=2000, timeout=self._poll_default)
            self._poll.start()
        self._player = player
        self._devices = devices or (lambda: ([], ""))
        self._set_device = set_device or (lambda d: None)
        self._segments: list[Segment] = []
        self._has_source = False
        self._line: int | None = None  # index of the current line
        self._stop_after = False
        self._stop_at: int | None = None
        self._wanted = ""
        self._device = None
        self._last_default = None
        self._names: dict[str, str] = {}
        player.setPitchCompensation(True)
        player.positionChanged.connect(self._on_position)
        player.playbackStateChanged.connect(
            lambda s: self.playing_changed.emit(s == QMediaPlayer.PlayingState))
        player.errorOccurred.connect(lambda _e, msg: self.error.emit(msg or "The recording could not be played."))

    # sources and lines
    def set_source(self, path: str | None) -> None:
        """The recording to play, or None (missing recording): every action is then a no-op."""
        self._player.stop()
        self._has_source = bool(path)
        self._player.setSource(QUrl.fromLocalFile(path) if path else QUrl())
        self._line, self._stop_at = None, None

    def has_source(self) -> bool:
        return self._has_source

    def set_segments(self, segments: list[Segment]) -> None:
        self._segments = list(segments)
        self._line = None

    # transport
    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlayingState

    def play(self) -> None:
        if self._has_source:
            self._player.play()

    def pause(self) -> None:
        if self._has_source:
            self._player.pause()

    def toggle(self) -> None:
        if self.is_playing():
            self.pause()
        else:
            self.play()

    def seek_ms(self, ms: int) -> None:
        if self._has_source:
            self._player.setPosition(max(0, int(ms)))

    def play_segment(self, seg_id: int) -> None:
        seg = next((s for s in self._segments if s.id == seg_id), None)
        if seg is not None and self._has_source:
            self.seek_ms(int(seg.start * 1000))
            self.play()

    def _jump(self, idx: int | None) -> None:
        if idx is not None and self._has_source:
            self.seek_ms(int(self._segments[idx].start * 1000))

    def prev_line(self) -> None:
        self._jump(step_line(self._segments, self._player.position() / 1000, -1))

    def next_line(self) -> None:
        self._jump(step_line(self._segments, self._player.position() / 1000, 1))

    def replay_line(self) -> None:
        if not self._has_source or not self._segments:
            return
        idx = self._line if self._line is not None else step_line(self._segments, self._player.position() / 1000, -1)
        if idx is not None:
            self._jump(idx)
            self._arm(idx)
            self.play()

    def set_rate(self, rate: float) -> None:
        rate = min(RATES, key=lambda r: abs(r - rate))
        self._player.setPitchCompensation(True)
        self._player.setPlaybackRate(rate)

    def set_stop_after_line(self, on: bool) -> None:
        self._stop_after = on
        self._arm(self._line)

    def _arm(self, idx: int | None) -> None:
        self._stop_at = int(self._segments[idx].end * 1000) if (self._stop_after and idx is not None) else None

    def _on_position(self, ms: int) -> None:
        # Stop first: when lines touch, the position past the end already belongs to the next line.
        if (self._stop_at is not None and self.is_playing() and self._line is not None
                and self._stop_at <= ms < self._stop_at + 1500):
            stop = self._stop_at
            self._stop_at = None
            self._player.pause()
            self._player.setPosition(stop)
            return
        self.position.emit(ms)
        idx = segment_at(self._segments, ms / 1000)
        if idx is not None and idx != self._line:
            self._line = idx
            self._arm(idx)
            self.line_changed.emit(self._segments[idx].id)

    # sound output
    def outputs(self) -> list[tuple[str, str]]:
        devs, _ = self._devices()
        return devs

    def set_output(self, device_id: str) -> None:
        self._wanted = device_id or ""
        self._apply_output()

    def devices_changed(self) -> None:
        self._apply_output()

    def _apply_output(self) -> None:
        devs, default = self._devices()
        self._names.update(dict(devs))
        chosen, fell_back = pick_output(devs, self._wanted, default)
        self._last_default = default
        if chosen != self._device:
            pos = self._player.position()
            self._set_device(chosen)
            self._device = chosen
            if self._player.position() != pos:
                self._player.setPosition(pos)
        if fell_back:
            name = self._names.get(self._wanted, "The chosen output")
            self.status.emit(f"{name} is not connected. Using the Windows default output.")

    def _poll_default(self) -> None:
        _, default = self._devices()
        if not self._wanted and default != self._last_default:
            self._apply_output()

    def _system_devices(self) -> tuple[list[tuple[str, str]], str]:
        devs = [(_device_id(d), d.description()) for d in QMediaDevices.audioOutputs()]
        return devs, _device_id(QMediaDevices.defaultAudioOutput())

    def _set_system_device(self, device_id: str) -> None:
        for d in QMediaDevices.audioOutputs():
            if _device_id(d) == device_id:
                self._audio.setDevice(d)
                return
        self._audio.setDevice(QMediaDevices.defaultAudioOutput())


# ---------- player bar ----------
def _icon(kind: str, colour: str, size: int = 20) -> QIcon:
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size * 2 / 24, size * 2 / 24)
    c = QColor(colour)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    path = QPainterPath()
    if kind == "play":
        path.moveTo(8, 5); path.lineTo(19, 12); path.lineTo(8, 19); path.closeSubpath()
    elif kind == "pause":
        path.addRect(QRectF(7, 5, 3.5, 14)); path.addRect(QRectF(13.5, 5, 3.5, 14))
    elif kind == "prev":
        path.addRect(QRectF(6, 5, 2, 14)); path.moveTo(20, 5); path.lineTo(9, 12); path.lineTo(20, 19); path.closeSubpath()
    elif kind == "next":
        path.addRect(QRectF(16, 5, 2, 14)); path.moveTo(4, 5); path.lineTo(15, 12); path.lineTo(4, 19); path.closeSubpath()
    elif kind == "stopline":
        path.addRect(QRectF(5, 5, 3, 14)); path.moveTo(11, 5); path.lineTo(20, 12); path.lineTo(11, 19); path.closeSubpath()
    p.drawPath(path)
    if kind == "replay":
        p.setPen(QPen(c, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(4, 4, 16, 16), 100 * 16, 290 * 16)
        p.drawPolyline([QPointF(4, 4), QPointF(4, 9), QPointF(9, 9)])
    p.end()
    return QIcon(pm)


class ProgressStrip(QWidget):
    """Thin track: played part, flag ticks; click or drag to seek."""

    seek = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(20)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.pos_ms, self.dur_ms, self.ticks = 0, 0, []

    def seek_at(self, x: float) -> None:
        if self.dur_ms > 0 and self.width() > 0:
            self.seek.emit(int(max(0.0, min(1.0, x / self.width())) * self.dur_ms))

    def mousePressEvent(self, e):
        self.seek_at(e.position().x())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self.seek_at(e.position().x())

    def paintEvent(self, _e):
        t = theme.current()["tokens"]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        y, w = self.height() / 2, self.width()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t["surface"]))
        p.drawRoundedRect(QRectF(0, y - 3, w, 6), 3, 3)
        if self.dur_ms:
            p.setBrush(QColor(t["accent"]))
            p.drawRoundedRect(QRectF(0, y - 3, w * self.pos_ms / self.dur_ms, 6), 3, 3)
        p.setBrush(QColor(t["flag_dot"]))
        for f in self.ticks:
            p.drawRoundedRect(QRectF(f * w - 1, y - 6, 2, 12), 1, 1)
        p.end()


class PlayerBar(QWidget):
    play_clicked = Signal()
    prev_clicked = Signal()
    next_clicked = Signal()
    replay_clicked = Signal()
    stop_after_toggled = Signal(bool)
    seek_requested = Signal(int)
    rate_chosen = Signal(float)
    output_chosen = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PlayerBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(80)

        def icon_button(name: str, tip: str, object_name: str = "Icon") -> QPushButton:
            b = QPushButton()
            b.setObjectName(object_name)
            b.setToolTip(tip)
            b.setIconSize(QSize(20, 20))
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("icon_kind", name)
            return b

        self.prev_btn = icon_button("prev", "Previous line (←)")
        self.replay_btn = icon_button("replay", "Replay this line (R)")
        self.play_btn = icon_button(
            "play", "Play or pause (Space)\n← → previous / next line · R replay line · S stop after each line\n"
            "E edit the playing line · F next line to check · [ ] slower / faster · Ctrl+K search", "Play")
        self.next_btn = icon_button("next", "Next line (→)")
        self.stop_btn = icon_button("stopline", "Stop after each line (S)")
        self.stop_btn.setCheckable(True)
        self.prev_btn.clicked.connect(self.prev_clicked)
        self.replay_btn.clicked.connect(self.replay_clicked)
        self.play_btn.clicked.connect(self.play_clicked)
        self.next_btn.clicked.connect(self.next_clicked)
        self.stop_btn.toggled.connect(self.stop_after_toggled)

        self.now = QLabel("00:00")
        self.now.setObjectName("Clock")
        self.total = QLabel("00:00")
        self.total.setObjectName("Clock")
        self.strip = ProgressStrip()
        self.strip.setMinimumWidth(160)
        self.strip.seek.connect(self.seek_requested)

        self.speed_buttons: list[QPushButton] = []
        self._speed_group = QButtonGroup(self)
        speed = QHBoxLayout()
        speed.setSpacing(0)
        for r in RATES:
            b = QPushButton(f"{r:g}×")
            b.setObjectName("Speed")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, r=r: self.rate_chosen.emit(r))
            self._speed_group.addButton(b)
            self.speed_buttons.append(b)
            speed.addWidget(b)
        self.speed_buttons[1].setChecked(True)

        self.output = QComboBox()
        self.output.setToolTip("Sound output")
        self.output.setMinimumWidth(150)
        self.output.setMaximumWidth(220)
        self.output.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.output.setMinimumContentsLength(14)
        self.output.activated.connect(lambda i: self.output_chosen.emit(self.output.itemData(i) or ""))


        row = QHBoxLayout(self)
        row.setContentsMargins(40, 0, 24, 0)
        row.setSpacing(12)
        for b in (self.prev_btn, self.replay_btn, self.play_btn, self.next_btn, self.stop_btn):
            row.addWidget(b)
        row.addSpacing(8)
        row.addWidget(self.now)
        row.addWidget(self.strip, 1)
        row.addWidget(self.total)
        row.addLayout(speed)
        row.addWidget(self.output)
        self._playing = False
        self.refresh_icons()

    def refresh_icons(self) -> None:
        t = theme.current()["tokens"]
        for b in (self.prev_btn, self.replay_btn, self.next_btn, self.stop_btn):
            b.setIcon(_icon(b.property("icon_kind"), t["ink"]))
        self.play_btn.setIcon(_icon("pause" if self._playing else "play", t["accent_label"]))

    def set_playing(self, playing: bool) -> None:
        self._playing = playing
        self.refresh_icons()

    def set_position(self, ms: int, duration_ms: int) -> None:
        self.strip.pos_ms, self.strip.dur_ms = ms, duration_ms
        self.now.setText(fmt_clock(ms / 1000))
        self.total.setText(fmt_clock(duration_ms / 1000))
        self.strip.update()

    def set_flags(self, starts_s: list[float], duration_s: float) -> None:
        self.strip.ticks = [s / duration_s for s in starts_s] if duration_s > 0 else []
        self.strip.update()

    def set_rate(self, rate: float) -> None:
        rate = min(RATES, key=lambda r: abs(r - rate))
        self.speed_buttons[RATES.index(rate)].setChecked(True)

    def set_stop_after(self, on: bool) -> None:
        self.stop_btn.blockSignals(True)
        self.stop_btn.setChecked(on)
        self.stop_btn.blockSignals(False)

    def set_outputs(self, devices: list[tuple[str, str]], current_id: str) -> None:
        self.output.blockSignals(True)
        self.output.clear()
        self.output.addItem("Windows default", "")
        for dev_id, name in devices:
            self.output.addItem(name, dev_id)
        i = self.output.findData(current_id)
        self.output.setCurrentIndex(i if i >= 0 else 0)
        self.output.blockSignals(False)

    def set_controls_enabled(self, on: bool) -> None:
        for w in (self.prev_btn, self.replay_btn, self.play_btn, self.next_btn, self.stop_btn, self.strip,
                  *self.speed_buttons):
            w.setEnabled(on)
