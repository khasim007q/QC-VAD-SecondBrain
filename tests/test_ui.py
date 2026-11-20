import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtMultimedia import QMediaPlayer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from classnotes import export, store  # noqa: E402
from classnotes.settings import Settings  # noqa: E402
from classnotes.store import Segment  # noqa: E402
from classnotes.ui.player import Playback  # noqa: E402

from test_player import FakePlayer  # noqa: E402
from test_store import make_record  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def window(qapp, tmp_path, rec=None, with_audio=True, open_it=True):
    from classnotes.ui.main_window import MainWindow

    rec = rec or make_record()
    if with_audio:
        audio = tmp_path / "class.mp3"
        audio.write_bytes(b"x")
        rec.audio_path = str(audio)
    store.save_record(rec, tmp_path)
    fake = FakePlayer()
    pb = Playback(player=fake, devices=lambda: ([("a", "Speakers")], "a"), set_device=lambda d: None)
    win = MainWindow(Settings(library_dir=str(tmp_path)), persist_settings=False, playback=pb)
    win._alert = lambda title, msg: win.alerts.append(msg)
    win._ask_edit = lambda: "discard"  # tests that close mid-edit must not block on the dialog
    win.alerts = []
    win.resize(1280, 800)
    win.show()
    win.activateWindow()
    qapp.processEvents()
    if open_it:
        win.open_class(rec.class_id)
        qapp.processEvents()
    return win, fake


def key(qapp, win, k, mod=Qt.NoModifier):
    QTest.keyClick(win, k, mod)
    qapp.processEvents()


def _wait_worker(qapp, win, timeout=20):
    t0 = time.time()
    while win.worker is not None and time.time() - t0 < timeout:
        qapp.processEvents()
        time.sleep(0.01)
    assert win.worker is None, "worker did not finish"


# ---------- opening and library ----------
def test_main_window_smoke(qapp, tmp_path):
    win, _ = window(qapp, tmp_path, with_audio=False)
    assert win.sidebar.classes.count() == 1
    assert win.record is not None and "In this verse" in win.lines.lines[0].english.text()
    assert win.banner.isVisibleTo(win)  # the recording doesn't exist
    assert win.minimumWidth() >= 1024 and win.minimumHeight() >= 700
    win.close()


def test_edit_saves_into_the_class_own_library_after_library_change(qapp, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    win, _ = window(qapp, a)
    other = make_record()
    other.title = "A different class in library B"
    store.save_record(other, b)
    win.settings.library_dir = str(b)  # user switched library in Settings
    win.apply_edit(0, "Corrected line")
    assert store.load_record(b / "2026-11-18").title == "A different class in library B"
    assert store.load_record(a / "2026-11-18").segments[0].text_edited == "Corrected line"
    win.close()


def test_failed_new_class_resets_header_and_class_can_be_reopened(qapp, tmp_path):
    win, _ = window(qapp, tmp_path, open_it=False)
    win._start(str(tmp_path / "missing.mp3"), "2026-11-19", "New one", None)
    _wait_worker(qapp, win)
    assert "processing" not in win.meta.text()
    win.sidebar.class_selected.emit("2026-11-18")
    qapp.processEvents()
    assert win.record is not None and win.record.class_id == "2026-11-18"
    win.close()


def test_failed_reprocess_reopens_the_class(qapp, tmp_path):
    win, _ = window(qapp, tmp_path)
    win._start(str(tmp_path / "missing.mp3"), "2026-11-18", "T", "2026-11-18")
    _wait_worker(qapp, win)
    assert win.alerts and "missing.mp3" in win.alerts[0]
    assert win.record is not None and win.record.class_id == "2026-11-18"
    assert "processing" not in win.meta.text()
    win.close()


def test_live_segments_are_appended_without_rebuilding(qapp, tmp_path):
    win, _ = window(qapp, tmp_path, open_it=False)
    win.worker = object()  # pretend a run is in progress
    win.lines.set_segments([])
    calls = []
    real = win.lines.set_segments
    win.lines.set_segments = lambda s: (calls.append(1), real(s))
    for i in range(50):
        win._on_segment(Segment(i, i, i + 0.5, "en", .9, f"line {i}", f"line {i}"))
    qapp.processEvents()
    assert calls == [] and len(win.lines.lines) == 50
    win.worker = None
    win.close()


# ---------- shortcuts ----------
def test_space_toggles_play_but_types_in_edit_box(qapp, tmp_path):
    win, fake = window(qapp, tmp_path)
    key(qapp, win, Qt.Key_Space)
    assert fake.state == QMediaPlayer.PlayingState
    key(qapp, win, Qt.Key_Space)
    assert fake.state == QMediaPlayer.PausedState
    win.lines.start_edit(0)
    QTest.keyClick(win.lines.editor, Qt.Key_Space)
    assert fake.state == QMediaPlayer.PausedState and win.lines.edit_text().endswith(" ")
    win.close()


def test_arrows_r_f_e_shortcuts(qapp, tmp_path):
    rec = make_record()
    rec.segments[1].lang_conf = 0.1  # flagged: language unsure
    win, fake = window(qapp, tmp_path, rec)
    fake.advance(13_000)
    key(qapp, win, Qt.Key_Right)
    assert fake.pos == 21_000
    key(qapp, win, Qt.Key_Left)
    assert fake.pos == 12_000
    fake.advance(15_000)
    key(qapp, win, Qt.Key_R)
    assert fake.pos == 12_000 and fake.state == QMediaPlayer.PlayingState
    key(qapp, win, Qt.Key_F)
    assert win.lines.playing == 1
    key(qapp, win, Qt.Key_E)
    assert win.lines.is_editing() and win.lines._editing == 1
    win.close()


def test_s_and_brackets(qapp, tmp_path):
    win, fake = window(qapp, tmp_path)
    key(qapp, win, Qt.Key_S)
    assert win.bar.stop_btn.isChecked() and win.settings.stop_after_line
    key(qapp, win, Qt.Key_BracketRight)
    assert fake.rate == 1.25 and win.settings.playback_rate == 1.25
    key(qapp, win, Qt.Key_BracketLeft)
    key(qapp, win, Qt.Key_BracketLeft)
    assert fake.rate == 0.75
    win.close()


def test_ctrl_k_focuses_search(qapp, tmp_path):
    win, _ = window(qapp, tmp_path)
    key(qapp, win, Qt.Key_K, Qt.ControlModifier)
    assert win.sidebar.search.hasFocus()
    win.close()


def test_shortcuts_are_noops_without_a_class_or_lines(qapp, tmp_path):
    win, fake = window(qapp, tmp_path, open_it=False)
    for k in (Qt.Key_Space, Qt.Key_Right, Qt.Key_Left, Qt.Key_R, Qt.Key_E, Qt.Key_F):
        key(qapp, win, k)
    assert fake.state == QMediaPlayer.StoppedState
    empty = make_record("2026-11-19")
    empty.segments = []
    store.save_record(empty, tmp_path)
    win.refresh_library()
    win.open_class("2026-11-19")
    for k in (Qt.Key_Right, Qt.Key_Left, Qt.Key_R, Qt.Key_E, Qt.Key_F):
        key(qapp, win, k)
    assert not win.lines.is_editing() and win.lines.empty_label.isVisibleTo(win)
    win.close()


# ---------- header, menus, counts ----------
def test_export_menu_lists_every_format(qapp, tmp_path):
    win, _ = window(qapp, tmp_path)
    assert [a.text() for a in win.export_menu.actions()] == [label for _, label, _ in export.FORMATS]
    win.close()


def test_more_menu_has_reprocess_open_folder_locate(qapp, tmp_path):
    win, _ = window(qapp, tmp_path)
    assert [a.text() for a in win.more_menu.actions()] == ["Re-process", "Open folder", "Locate recording"]
    win.close()


def test_to_check_count_updates_after_edit_and_looks_fine(qapp, tmp_path):
    rec = make_record()
    rec.segments[0].lang_conf = 0.1
    rec.segments[1].lang_conf = 0.1
    win, _ = window(qapp, tmp_path, rec)
    assert "2 to check" in win.meta.text()
    win.apply_edit(0, "Fixed.")
    assert "1 to check" in win.meta.text()
    win.lines.lines[1].looks_fine_btn.click()
    qapp.processEvents()
    assert "0 to check" in win.meta.text() and win.record.segments[1].checked
    assert store.load_record(tmp_path / "2026-11-18").segments[1].checked
    win.close()


def test_missing_recording_disables_player_but_allows_edits(qapp, tmp_path):
    win, fake = window(qapp, tmp_path, with_audio=False)
    assert win.banner.isVisibleTo(win) and not win.bar.play_btn.isEnabled()
    key(qapp, win, Qt.Key_Space)
    key(qapp, win, Qt.Key_Right)
    assert fake.state == QMediaPlayer.StoppedState and fake.pos == 0
    win.apply_edit(0, "Still editable")
    assert store.load_record(tmp_path / "2026-11-18").segments[0].text_edited == "Still editable"
    win.close()


def test_theme_switch_keeps_edit_and_playing_line(qapp, tmp_path):
    win, fake = window(qapp, tmp_path)
    fake.advance(22_000)
    win.lines.start_edit(1)
    QTest.keyClicks(win.lines.editor, " typed")
    win.settings.theme = "dark"
    assert win.apply_theme() == "dark"
    assert win.lines.is_editing() and win.lines.edit_text().endswith(" typed") and win.lines.playing == 1
    win.settings.theme = "light"
    win.apply_theme()
    win.close()


def test_settings_dialog_theme_round_trip(qapp):
    from classnotes.ui.dialogs import SettingsDialog

    s = Settings(theme="dark")
    dlg = SettingsDialog(s)
    assert dlg.theme.currentData() == "dark"
    dlg.theme.setCurrentIndex(dlg.theme.findData("system"))
    dlg.apply(s)
    assert s.theme == "system"


# ---------- playback wiring ----------
def test_clicking_a_line_plays_from_its_start(qapp, tmp_path):
    win, fake = window(qapp, tmp_path)
    QTest.mouseClick(win.lines.lines[1], Qt.LeftButton, pos=QPoint(20, 10))
    qapp.processEvents()
    assert fake.pos == 21_000 and fake.state == QMediaPlayer.PlayingState
    win.close()


def test_search_result_opens_line_without_playing(qapp, tmp_path):
    win, fake = window(qapp, tmp_path, open_it=False)
    win.sidebar.hit_selected.emit("2026-11-18", 1)
    qapp.processEvents()
    assert win.record.class_id == "2026-11-18" and win.lines.playing == 1
    assert fake.pos == 21_000 and fake.state != QMediaPlayer.PlayingState
    win.close()


def test_editing_pauses_and_save_resumes(qapp, tmp_path):
    win, fake = window(qapp, tmp_path)
    fake.advance(13_000)
    win.playback.play()
    key(qapp, win, Qt.Key_E)
    assert fake.state == QMediaPlayer.PausedState
    QTest.keyClick(win.lines.editor, Qt.Key_Return)
    assert fake.state == QMediaPlayer.PlayingState
    key(qapp, win, Qt.Key_E)
    QTest.keyClick(win.lines.editor, Qt.Key_Escape)
    assert fake.state == QMediaPlayer.PlayingState
    win.close()


# ---------- review fixes ----------
def test_edit_links_are_hidden_while_processing(qapp, tmp_path):
    win, _ = window(qapp, tmp_path, open_it=False)
    win.worker = object()
    win.lines.set_segments([])
    win.lines.set_editable(False)
    win._on_segment(Segment(0, 1, 2, "ur", .9, "اردو", "Urdu"))
    assert win.lines.start_edit(0) is False
    win.worker = None
    win.close()


@pytest.mark.parametrize("answer", ["save", "discard", "cancel"])
def test_switching_class_mid_edit_asks_first(qapp, tmp_path, answer):
    win, _ = window(qapp, tmp_path)
    store.save_record(make_record("2026-11-11"), tmp_path)
    win.refresh_library()
    win._ask_edit = lambda: answer
    win.lines.start_edit(0)
    win.lines.editor.setPlainText("Half typed")
    win.sidebar.class_selected.emit("2026-11-11")
    qapp.processEvents()
    saved = store.load_record(tmp_path / "2026-11-18").segments[0].text_edited
    if answer == "cancel":
        assert win.record.class_id == "2026-11-18" and win.lines.is_editing()
    else:
        assert win.record.class_id == "2026-11-11" and not win.lines.is_editing()
        assert saved == ("Half typed" if answer == "save" else None)
    win.close()


def test_output_list_refreshes_in_the_bar(qapp, tmp_path):
    from classnotes.ui.main_window import MainWindow

    store.save_record(make_record(), tmp_path)
    state = {"devices": [("a", "Speakers")]}
    pb = Playback(player=FakePlayer(), devices=lambda: (state["devices"], "a"), set_device=lambda d: None)
    win = MainWindow(Settings(library_dir=str(tmp_path)), persist_settings=False, playback=pb)
    assert win.bar.output.count() == 2  # Windows default + Speakers
    state["devices"] = [("a", "Speakers"), ("c", "USB headset")]
    pb.devices_changed()
    assert win.bar.output.count() == 3 and win.bar.output.itemText(2) == "USB headset"
    win.close()


def test_search_sees_edits_made_this_session(qapp, tmp_path):
    win, _ = window(qapp, tmp_path)
    win.apply_edit(0, "A brand new wording")
    win.sidebar.search.setText("brand new")
    win.sidebar.flush_search()
    assert any(win.sidebar.results.item(i).data(Qt.UserRole) == ("2026-11-18", 0)
               for i in range(win.sidebar.results.count()))
    win.close()


def test_dark_theme_at_startup_draws_light_icons(qapp, tmp_path):
    from classnotes.ui import app as app_mod
    from classnotes.ui import theme

    store.save_record(make_record(), tmp_path)
    win = app_mod.build_window(qapp, Settings(library_dir=str(tmp_path), theme="dark"), persist=False)
    img = win.bar.next_btn.icon().pixmap(40, 40).toImage()
    ink = max((img.pixelColor(x, y) for x in range(40) for y in range(40)), key=lambda c: c.alpha())
    assert ink.lightness() > 150  # bone-coloured, not near-black
    theme.apply(qapp, Settings(theme="light"))
    win.close()
