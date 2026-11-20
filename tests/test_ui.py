import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from classnotes import store  # noqa: E402
from classnotes.settings import Settings  # noqa: E402
from classnotes.store import Segment  # noqa: E402
from classnotes.ui.segment_view import render_segments_html, segment_at  # noqa: E402

from test_store import make_record  # noqa: E402


def test_render_html_escapes_and_marks():
    segs = [
        Segment(0, 1, 5, "ur", .9, "اس <آیت>", "In <this> verse"),
        Segment(1, 6, 9, "en", .9, "Question?", "Question?", text_edited="Edited question?"),
        Segment(2, 10, 15, "ar", .9, "الحمد لله", ""),
    ]
    html = render_segments_html(segs, current_id=1)
    assert "In &lt;this&gt; verse" in html and "<this>" not in html
    assert 'dir="rtl"' in html and "اس &lt;آیت&gt;" in html
    assert 'href="seek:0"' in html and 'href="edit:1"' in html
    assert "Edited question?" in html and "edited" in html
    assert "Recitation" in html and "not translated" in html
    assert 'name="seg-1"' in html


def test_render_empty():
    assert "No speech found" in render_segments_html([], None)


def test_segment_at():
    segs = make_record().segments
    assert segment_at(segs, 15.0) == 0
    assert segment_at(segs, 20.7) is None  # in the gap
    assert segment_at(segs, 22.0) == 1


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_main_window_smoke(qapp, tmp_path):
    from classnotes.ui.main_window import MainWindow

    store.save_record(make_record(), tmp_path)
    win = MainWindow(Settings(library_dir=str(tmp_path)), persist_settings=False)
    assert win.library.count() == 1
    win.library.setCurrentRow(0)
    qapp.processEvents()
    assert win.record is not None
    assert "In this verse" in win.view.toHtml()
    assert win.missing_banner.isVisibleTo(win)  # audio path doesn't exist
    win.close()


def _wait_worker(qapp, win, timeout=20):
    import time

    t0 = time.time()
    while win.worker is not None and time.time() - t0 < timeout:
        qapp.processEvents()
        time.sleep(0.01)
    assert win.worker is None, "worker did not finish"


def test_edit_saves_into_the_class_own_library_after_library_change(qapp, tmp_path):
    from classnotes.ui.main_window import MainWindow

    a, b = tmp_path / "a", tmp_path / "b"
    store.save_record(make_record(), a)
    other = make_record()
    other.title = "A different class in library B"
    store.save_record(other, b)
    win = MainWindow(Settings(library_dir=str(a)), persist_settings=False)
    win.library.setCurrentRow(0)
    qapp.processEvents()
    win.settings.library_dir = str(b)  # user switched library in Settings
    win.apply_edit(0, "Corrected line")
    assert store.load_record(b / "2026-11-18").title == "A different class in library B"
    assert store.load_record(a / "2026-11-18").segments[0].text_edited == "Corrected line"
    win.close()


def test_failed_new_class_resets_header_and_row_can_be_reopened(qapp, tmp_path):
    from classnotes.ui.main_window import MainWindow

    store.save_record(make_record(), tmp_path)
    win = MainWindow(Settings(library_dir=str(tmp_path)), persist_settings=False)
    win._alert = lambda title, msg: None
    win.library.setCurrentRow(0)
    qapp.processEvents()
    win._start(str(tmp_path / "missing.mp3"), "2026-11-19", "New one", None)
    _wait_worker(qapp, win)
    assert "processing" not in win.header.text()
    win.library.setCurrentRow(0)  # click the same class again
    qapp.processEvents()
    assert win.record is not None and win.record.class_id == "2026-11-18"
    win.close()


def test_failed_reprocess_reopens_the_class(qapp, tmp_path):
    from classnotes.ui.main_window import MainWindow

    store.save_record(make_record(), tmp_path)
    win = MainWindow(Settings(library_dir=str(tmp_path)), persist_settings=False)
    alerts = []
    win._alert = lambda title, msg: alerts.append(msg)
    win._start(str(tmp_path / "missing.mp3"), "2026-11-18", "T", "2026-11-18")
    _wait_worker(qapp, win)
    assert alerts and "missing.mp3" in alerts[0]
    assert win.record is not None and win.record.class_id == "2026-11-18"
    assert "processing" not in win.header.text()
    win.close()


def test_moving_to_the_next_segment_does_not_rebuild_the_page(qapp, tmp_path):
    from classnotes.ui.main_window import MainWindow

    store.save_record(make_record(), tmp_path)
    win = MainWindow(Settings(library_dir=str(tmp_path)), persist_settings=False)
    win.library.setCurrentRow(0)
    qapp.processEvents()
    calls = []
    real = win.view.setHtml
    win.view.setHtml = lambda html: (calls.append(1), real(html))
    win._position_changed(15_000)
    win._position_changed(22_000)
    assert calls == []
    sels = win.view.extraSelections()
    assert len(sels) == 1 and "What do you think?" in sels[0].cursor.selectedText()
    win.close()


def test_live_segments_are_drawn_in_batches(qapp, tmp_path):
    import time

    from classnotes.ui.main_window import MainWindow

    win = MainWindow(Settings(library_dir=str(tmp_path)), persist_settings=False)
    win.worker = object()  # pretend a run is in progress
    calls = []
    real = win.view.setHtml
    win.view.setHtml = lambda html: (calls.append(1), real(html))
    for i in range(50):
        win._on_segment(Segment(i, i, i + 0.5, "en", .9, f"line {i}", f"line {i}"))
    assert len(calls) <= 1
    t0 = time.time()
    while time.time() - t0 < 1.5:
        qapp.processEvents()
        time.sleep(0.01)
    assert 1 <= len(calls) <= 2
    assert "line 49" in win.view.toPlainText()
    win.worker = None
    win.close()
