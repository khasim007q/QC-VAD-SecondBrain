import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from classnotes.store import Segment  # noqa: E402
from classnotes.ui.line_view import LineList  # noqa: E402

URDU = "یہ ایک لمبا جملہ ہے جس میں بہت سارے الفاظ ہیں تاکہ تناسب ٹھیک رہے"


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def segs(n=5):
    return [Segment(i, i * 10.0, i * 10.0 + 8, "ur", 0.99, URDU, f"English line number {i} with enough words.")
            for i in range(n)]


def make(qapp, data=None):
    lst = LineList()
    lst.resize(900, 600)
    lst.show()
    lst.set_segments(data if data is not None else segs())
    qapp.processEvents()
    return lst


def test_800_lines_open_in_under_a_second(qapp):
    from classnotes.settings import Settings
    from classnotes.ui import theme

    theme.apply(qapp, Settings(theme="light"))  # the real stylesheet costs time per widget
    long_ur = " ".join([URDU] * 6)  # Session 19 lines are 20-25 s of speech
    data = [Segment(i, i * 10.0, i * 10.0 + 8, "ur", 0.99, long_ur, "An English translation " * 12)
            for i in range(800)]
    lst = LineList()
    lst.resize(1100, 700)
    lst.show()
    try:
        t0 = time.perf_counter()
        lst.set_segments(data)
        qapp.processEvents()
        assert time.perf_counter() - t0 < 1.0
        t0 = time.perf_counter()
        lst.set_playing(5)
        lst.set_playing(6)
        qapp.processEvents()
        assert (time.perf_counter() - t0) / 2 < 0.05  # moving the highlight stays instant
        lst.scroll_to(790)  # a far line is reachable right away
        assert 790 in lst.lines
    finally:
        qapp.setStyleSheet("")


def test_playing_property_moves_without_rebuilding(qapp):
    lst = make(qapp)
    before = {i: id(w) for i, w in lst.lines.items()}
    lst.set_playing(1)
    lst.set_playing(2)
    assert {i: id(w) for i, w in lst.lines.items()} == before
    assert lst.lines[2].property("playing") is True and lst.lines[1].property("playing") is False


def test_clicking_a_line_requests_a_seek(qapp):
    lst = make(qapp)
    got = []
    lst.seek_requested.connect(got.append)
    QTest.mouseClick(lst.lines[3], Qt.LeftButton, pos=QPoint(20, 10))
    assert got == [3]


def test_edit_enter_saves_shift_enter_newline_esc_cancels(qapp):
    lst = make(qapp)
    saved, cancelled = [], []
    lst.edit_saved.connect(lambda i, t: saved.append((i, t)))
    lst.edit_cancelled.connect(cancelled.append)
    assert lst.start_edit(1) and lst.is_editing()
    ed = lst.editor
    ed.selectAll()
    QTest.keyClicks(ed, "Fixed")
    QTest.keyClick(ed, Qt.Key_Return, Qt.ShiftModifier)
    QTest.keyClicks(ed, "second")
    QTest.keyClick(ed, Qt.Key_Return)
    assert saved == [(1, "Fixed\nsecond")] and not lst.is_editing()
    lst.start_edit(2)
    QTest.keyClick(lst.editor, Qt.Key_Escape)
    assert cancelled == [2] and not lst.is_editing()


def test_saving_the_machine_text_unchanged_clears_the_edit(qapp):
    lst = make(qapp)
    saved = []
    lst.edit_saved.connect(lambda i, t: saved.append((i, t)))
    lst.start_edit(0)
    QTest.keyClick(lst.editor, Qt.Key_Return)
    assert saved == [(0, None)]


def test_long_line_edit_saves_whole_text(qapp):
    data = segs(2)
    data[0].text = "word " * 120  # 600 characters
    lst = make(qapp, data)
    saved = []
    lst.edit_saved.connect(lambda i, t: saved.append(t))
    lst.start_edit(0)
    lst.editor.moveCursor(lst.editor.textCursor().MoveOperation.End)
    qapp.processEvents()
    line_h = lst.editor.fontMetrics().lineSpacing()
    assert lst.editor.height() >= 6 * line_h  # opens tall enough for the whole 600-character line
    QTest.keyClicks(lst.editor, " end")
    QTest.keyClick(lst.editor, Qt.Key_Return)
    assert saved[0].endswith(" end") and len(saved[0]) == 604


def test_flagged_line_shows_reason_and_looks_fine(qapp):
    data = segs(2)
    data[1].lang_conf = 0.1
    lst = make(qapp, data)
    w = lst.lines[1]
    assert w.property("flagged") is True and w.flag_label.text() == "Check: language unsure"
    got = []
    lst.marked_checked.connect(got.append)
    w.looks_fine_btn.click()
    assert got == [1]


def test_edited_line_offers_revert(qapp):
    data = segs(2)
    data[0].text_edited = "Better English."
    lst = make(qapp, data)
    w = lst.lines[0]
    assert w.english.text() == "Better English." and w.revert_btn.isVisibleTo(w)
    got = []
    lst.edit_saved.connect(lambda i, t: got.append((i, t)))
    w.revert_btn.click()
    assert got == [(0, None)]


def test_recitation_has_no_edit_link(qapp):
    data = [Segment(0, 1, 5, "ar", 0.9, "الحمد لله رب العالمين", "")]
    lst = make(qapp, data)
    w = lst.lines[0]
    assert not w.edit_btn.isVisibleTo(w) and "Recitation" in w.tag.text()
    assert lst.start_edit(0) is False


def test_user_scroll_stops_following_and_back_button_resumes(qapp):
    lst = make(qapp, segs(60))
    lst.set_playing(30)
    qapp.processEvents()
    assert lst.following and lst.verticalScrollBar().value() > 0
    lst.verticalScrollBar().setValue(0)  # the user scrolled away
    assert not lst.following and lst.back_btn.isVisibleTo(lst)
    lst.back_btn.click()
    assert lst.following and not lst.back_btn.isVisibleTo(lst)


def test_clicks_on_other_lines_ignored_while_editing(qapp):
    lst = make(qapp)
    got = []
    lst.seek_requested.connect(got.append)
    lst.start_edit(1)
    QTest.mouseClick(lst.lines[3], Qt.LeftButton, pos=QPoint(20, 10))
    assert got == [] and lst.is_editing()


def test_update_segment_refreshes_text_and_flag(qapp):
    data = segs(2)
    data[1].lang_conf = 0.1
    lst = make(qapp, data)
    data[1].checked = True
    data[1].text_edited = "Now edited."
    lst.update_segment(1)
    w = lst.lines[1]
    assert w.property("flagged") is False and w.english.text() == "Now edited."


def test_empty_class_shows_no_speech(qapp):
    lst = make(qapp, [])
    assert lst.empty_label.isVisibleTo(lst) and "No speech found" in lst.empty_label.text()
    assert lst.start_edit(0) is False


def test_not_editable_while_processing(qapp):
    lst = make(qapp)
    lst.set_editable(False)
    w = lst.lines[1]
    assert lst.start_edit(1) is False and not w.edit_btn.isVisibleTo(w)
    lst.set_editable(True)
    assert w.edit_btn.isVisibleTo(w) and lst.start_edit(1)
