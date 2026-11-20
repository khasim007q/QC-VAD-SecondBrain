import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtMultimedia import QMediaPlayer  # noqa: E402

from classnotes.store import Segment  # noqa: E402
from classnotes.ui.player import (  # noqa: E402
    RATES, Playback, PlayerBar, pick_output, segment_at, step_line, step_rate,
)

from test_store import make_record  # noqa: E402

SEGS = [Segment(0, 10.0, 20.0, "ur", .9, "a", "A"), Segment(1, 20.0, 30.0, "ur", .9, "b", "B"),
        Segment(2, 40.0, 50.0, "ur", .9, "c", "C")]


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


# ---------- pure helpers ----------
def test_segment_at():
    segs = make_record().segments
    assert segment_at(segs, 15.0) == 0
    assert segment_at(segs, 20.7) is None  # in the gap
    assert segment_at(segs, 22.0) == 1


def test_step_line_previous_restarts_the_line_after_a_second():
    assert step_line(SEGS, 25.0, -1) == 1   # 5 s into line 1: back to its start
    assert step_line(SEGS, 20.5, -1) == 0   # just started line 1: previous line
    assert step_line(SEGS, 35.0, -1) == 1   # in the gap after line 1
    assert step_line(SEGS, 10.2, -1) == 0   # first line stays first


def test_step_line_next():
    assert step_line(SEGS, 12.0, 1) == 1
    assert step_line(SEGS, 35.0, 1) == 2
    assert step_line(SEGS, 45.0, 1) is None
    assert step_line(SEGS, 0.0, 1) == 0
    assert step_line([], 5.0, 1) is None and step_line([], 5.0, -1) is None


def test_rates_and_step_rate_clamp():
    assert RATES == (0.75, 1.0, 1.25, 1.5)
    assert step_rate(1.0, 1) == 1.25 and step_rate(1.5, 1) == 1.5 and step_rate(0.75, -1) == 0.75
    assert step_rate(1.1, 1) == 1.25  # an odd stored value snaps to the list


def test_pick_output():
    devs = [("a", "Speakers"), ("b", "Headset")]
    assert pick_output(devs, "b", "a") == ("b", False)
    assert pick_output(devs, "gone", "a") == ("a", True)
    assert pick_output(devs, "", "a") == ("a", False)


# ---------- controller with a fake media player ----------
class FakePlayer(QObject):
    positionChanged = Signal(int)
    playbackStateChanged = Signal(object)
    durationChanged = Signal(int)
    errorOccurred = Signal(object, str)
    mediaStatusChanged = Signal(object)

    def __init__(self, loading=False):
        super().__init__()
        self.pos, self.state, self.rate, self.pitch, self.src = 0, QMediaPlayer.StoppedState, 1.0, False, None
        self.loading = loading
        self.status = QMediaPlayer.LoadedMedia

    def setSource(self, url):
        self.src = url
        self.status = QMediaPlayer.LoadingMedia if self.loading else QMediaPlayer.LoadedMedia

    def mediaStatus(self): return self.status

    def finish_loading(self):
        self.status = QMediaPlayer.LoadedMedia
        self.mediaStatusChanged.emit(self.status)

    def setAudioOutput(self, out): pass
    def play(self): self.state = QMediaPlayer.PlayingState; self.playbackStateChanged.emit(self.state)
    def pause(self): self.state = QMediaPlayer.PausedState; self.playbackStateChanged.emit(self.state)
    def stop(self): self.state = QMediaPlayer.StoppedState
    def playbackState(self): return self.state
    def position(self): return self.pos
    def duration(self): return 60_000

    def setPosition(self, ms):
        if self.status == QMediaPlayer.LoadingMedia:
            return  # like Qt 6.12: a seek while loading is ignored
        self.pos = ms
        self.positionChanged.emit(ms)

    def setPlaybackRate(self, r): self.rate = r
    def setPitchCompensation(self, on): self.pitch = on

    def advance(self, ms):
        self.pos = ms
        self.positionChanged.emit(ms)


def make_playback(devices=None, segs=None, loading=False):
    fake = FakePlayer(loading=loading)
    state = {"devices": devices or [("a", "Speakers"), ("b", "JBL Quantum 300")], "default": "a", "set": []}
    pb = Playback(player=fake, devices=lambda: (state["devices"], state["default"]),
                  set_device=lambda d: state["set"].append(d))
    pb.set_segments(segs or SEGS)
    pb.set_source("C:/class.mp3")
    return pb, fake, state


def test_stop_after_line_pauses_at_the_line_end(qapp):
    pb, fake, _ = make_playback()
    pb.set_stop_after_line(True)
    pb.seek_ms(10_000)
    pb.play()
    fake.advance(15_000)
    assert fake.state == QMediaPlayer.PlayingState
    fake.advance(20_050)
    assert fake.state == QMediaPlayer.PausedState and fake.pos == 19_999  # parked inside the line


def test_without_stop_after_line_playback_continues(qapp):
    pb, fake, _ = make_playback()
    pb.seek_ms(10_000)
    pb.play()
    fake.advance(20_050)
    assert fake.state == QMediaPlayer.PlayingState


def test_rate_sets_pitch_compensation(qapp):
    pb, fake, _ = make_playback()
    pb.set_rate(1.25)
    assert fake.rate == 1.25 and fake.pitch is True


def test_line_navigation_seeks_to_line_starts(qapp):
    pb, fake, _ = make_playback()
    fake.advance(25_000)
    pb.prev_line()
    assert fake.pos == 20_000
    pb.next_line()
    assert fake.pos == 40_000
    fake.advance(45_000)
    pb.replay_line()
    assert fake.pos == 40_000 and fake.state == QMediaPlayer.PlayingState


def test_line_changed_signal(qapp):
    pb, fake, _ = make_playback()
    seen = []
    pb.line_changed.connect(seen.append)
    fake.advance(12_000)
    fake.advance(13_000)
    fake.advance(35_000)  # gap keeps the last line
    fake.advance(41_000)
    assert seen == [0, 2]


def test_unplugged_output_falls_back_and_keeps_position(qapp):
    pb, fake, state = make_playback()
    msgs = []
    pb.status.connect(msgs.append)
    pb.set_output("b")
    assert state["set"][-1] == "b"
    fake.advance(33_000)
    state["devices"] = [("a", "Speakers")]
    pb.devices_changed()
    assert state["set"][-1] == "a" and fake.pos == 33_000
    assert msgs and "JBL Quantum 300" in msgs[-1]


def test_windows_default_change_is_followed(qapp):
    pb, fake, state = make_playback()
    pb.set_output("")
    state["default"] = "b"
    pb.devices_changed()
    assert state["set"][-1] == "b"


def test_no_source_makes_actions_noops(qapp):
    pb, fake, _ = make_playback()
    pb.set_source(None)
    pb.toggle()
    pb.next_line()
    pb.replay_line()
    assert fake.state == QMediaPlayer.StoppedState and fake.pos == 0


# ---------- player bar ----------
def test_bar_speed_and_seek_signals(qapp):
    bar = PlayerBar()
    bar.resize(1200, 80)
    rates, seeks = [], []
    bar.rate_chosen.connect(rates.append)
    bar.seek_requested.connect(seeks.append)
    bar.speed_buttons[2].click()
    assert rates == [1.25]
    bar.set_position(0, 100_000)
    bar.strip.resize(400, 20)
    bar.strip.seek_at(200)
    assert seeks == [50_000]


def test_bar_shows_flag_ticks(qapp):
    bar = PlayerBar()
    bar.set_flags([30.0, 60.0], 120.0)
    assert bar.strip.ticks == [0.25, 0.5]


def test_a_jump_past_the_stop_point_does_not_pause(qapp):
    pb, fake, _ = make_playback()
    pb.set_stop_after_line(True)
    pb.seek_ms(10_000)
    pb.play()
    pb.seek_ms(45_000)  # the user jumped to line 2
    assert fake.state == QMediaPlayer.PlayingState
    fake.advance(50_100)
    assert fake.state == QMediaPlayer.PausedState and fake.pos == 49_999


TOUCH = [Segment(0, 10.0, 20.0, "ur", .9, "a", "A"), Segment(1, 20.0, 30.0, "ur", .9, "b", "B")]


def test_stop_keeps_the_stopped_line_current_when_lines_touch(qapp):
    pb, fake, _ = make_playback(segs=TOUCH)
    seen = []
    pb.line_changed.connect(seen.append)
    pb.set_stop_after_line(True)
    pb.seek_ms(10_000)
    pb.play()
    fake.advance(19_900)
    fake.advance(20_050)
    assert fake.state == QMediaPlayer.PausedState and seen == [0]
    pb.replay_line()
    assert fake.pos == 10_000


@pytest.mark.parametrize("gap", [0.0, 1.2])
def test_next_line_jumps_instead_of_stopping(qapp, gap):
    segs = [Segment(0, 10.0, 20.0, "ur", .9, "a", "A"), Segment(1, 20.0 + gap, 30.0, "ur", .9, "b", "B")]
    pb, fake, _ = make_playback(segs=segs)
    pb.set_stop_after_line(True)
    pb.seek_ms(15_000)
    pb.play()
    pb.next_line()
    assert fake.state == QMediaPlayer.PlayingState and fake.pos == int((20.0 + gap) * 1000)


def test_replaying_a_stopped_line_stops_again(qapp):
    pb, fake, _ = make_playback()  # SEGS has a gap after line 1
    pb.set_stop_after_line(True)
    pb.seek_ms(20_000)
    pb.play()
    fake.advance(29_900)
    fake.advance(30_050)
    assert fake.state == QMediaPlayer.PausedState
    pb.play_segment(1)
    assert fake.state == QMediaPlayer.PlayingState and fake.pos == 20_000
    fake.advance(29_900)
    fake.advance(30_050)
    assert fake.state == QMediaPlayer.PausedState


def test_seek_while_loading_is_applied_once_loaded(qapp):
    pb, fake, _ = make_playback(loading=True)
    pb.seek_ms(12_000)
    assert fake.pos == 0
    fake.finish_loading()
    assert fake.pos == 12_000


def test_output_list_changes_are_announced(qapp):
    pb, fake, state = make_playback()
    got = []
    pb.outputs_changed.connect(lambda: got.append(pb.outputs()))
    state["devices"] = [("a", "Speakers"), ("b", "JBL Quantum 300"), ("c", "USB headset")]
    pb.devices_changed()
    assert got and ("c", "USB headset") in got[-1]


def test_bar_has_no_output_picker(qapp):
    bar = PlayerBar()
    assert not hasattr(bar, "output") and not hasattr(bar, "output_chosen")


def test_speed_buttons_form_one_rounded_control(qapp):
    bar = PlayerBar()
    assert [b.property("segment") for b in bar.speed_buttons] == ["first", "mid", "mid", "last"]
