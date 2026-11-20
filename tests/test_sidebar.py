import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from classnotes.ui.sidebar import Sidebar  # noqa: E402

from test_store import make_record  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def make(qapp):
    a = make_record("2026-11-18")
    a.segments[0].text_edited = "In this verse, the Sunnah"
    b = make_record("2026-11-11")
    b.title = "Session 18"
    sb = Sidebar()
    sb.resize(280, 700)
    sb.show()
    sb.set_records([a, b])
    qapp.processEvents()
    return sb


def click_item(lst, row):
    rect = lst.visualItemRect(lst.item(row))
    QTest.mouseClick(lst.viewport(), Qt.LeftButton, pos=rect.center())


def test_classes_listed_and_click_emits(qapp):
    sb = make(qapp)
    got = []
    sb.class_selected.connect(got.append)
    assert sb.classes.count() == 2
    click_item(sb.classes, 1)
    click_item(sb.classes, 1)  # clicking the selected class again still opens it
    assert got == ["2026-11-11", "2026-11-11"]


def test_select_class_emits_nothing(qapp):
    sb = make(qapp)
    got = []
    sb.class_selected.connect(got.append)
    sb.select_class("2026-11-11")
    assert got == [] and sb.classes.currentItem().data(Qt.UserRole) == "2026-11-11"


def test_search_results_replace_the_list_and_click_opens_line(qapp):
    sb = make(qapp)
    got = []
    sb.hit_selected.connect(lambda c, s: got.append((c, s)))
    sb.search.setText("Sunnah")
    sb.flush_search()
    assert sb.results.isVisibleTo(sb) and not sb.classes.isVisibleTo(sb)
    rows = [i for i in range(sb.results.count()) if sb.results.item(i).data(Qt.UserRole)]
    assert len(rows) == 1
    click_item(sb.results, rows[0])
    assert got == [("2026-11-18", 0)]


def test_escape_restores_the_class_list(qapp):
    sb = make(qapp)
    sb.search.setText("Sunnah")
    sb.flush_search()
    QTest.keyClick(sb.search, Qt.Key_Escape)
    assert sb.search.text() == "" and sb.classes.isVisibleTo(sb) and not sb.results.isVisibleTo(sb)


def test_one_letter_keeps_the_class_list(qapp):
    sb = make(qapp)
    sb.search.setText("S")
    sb.flush_search()
    assert sb.classes.isVisibleTo(sb)


def test_no_results_says_so(qapp):
    sb = make(qapp)
    sb.search.setText("zzzz")
    sb.flush_search()
    assert sb.results.count() == 1 and "No lines match" in sb.results.item(0).text()
