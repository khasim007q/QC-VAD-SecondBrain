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
