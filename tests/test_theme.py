import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402

from classnotes.ui import theme  # noqa: E402
from classnotes.ui.theme import DARK, LIGHT, contrast, pick_fonts, qss, resolve  # noqa: E402


@pytest.mark.parametrize("t", [LIGHT, DARK], ids=["light", "dark"])
def test_text_pairs_meet_contrast(t):
    assert contrast(t["ink"], t["page"]) >= 7 and contrast(t["ink"], t["panel"]) >= 7
    assert contrast(t["muted"], t["page"]) >= 4.5 and contrast(t["muted"], t["panel"]) >= 4.5
    assert contrast(t["flag_label"], t["panel"]) >= 4.5 and contrast(t["flag_label"], t["page"]) >= 4.5
    assert contrast(t["accent_label"], t["accent"]) >= 4.5
    assert contrast(t["accent"], t["page"]) >= 3


def test_contrast_known_values():
    assert round(contrast("#000000", "#ffffff"), 1) == 21.0
    assert contrast("#777777", "#777777") == pytest.approx(1.0)


def test_resolve_follows_windows_only_for_system():
    assert resolve("system", Qt.ColorScheme.Dark) == "dark"
    assert resolve("system", Qt.ColorScheme.Light) == "light"
    assert resolve("system", Qt.ColorScheme.Unknown) == "light"
    assert resolve("light", Qt.ColorScheme.Dark) == "light"
    assert resolve("dark", Qt.ColorScheme.Light) == "dark"


@pytest.mark.parametrize("t", [LIGHT, DARK], ids=["light", "dark"])
def test_qss_uses_the_tokens(t):
    css = qss(t, pick_fonts({"Segoe UI"}))
    for key in ("page", "panel", "ink", "accent", "muted", "flag_label"):
        assert t[key] in css
    assert "{page}" not in css and "{ink}" not in css
    for name in ("#Sidebar", "#Header", "#LineList", "#Line", "#PlayerBar", 'kind="primary"', "#Notice", "#Banner"):
        assert name in css


def test_pick_fonts_prefers_nastaliq_and_falls_back():
    assert pick_fonts({"Segoe UI", "Urdu Typesetting"})["urdu"] == "Urdu Typesetting"
    f = pick_fonts({"Segoe UI", "Cascadia Mono"})
    assert f == {"ui": "Segoe UI", "mono": "Cascadia Mono", "urdu": "Segoe UI", "arabic": "Segoe UI"}
    assert pick_fonts(set())["ui"] == "Segoe UI"


def test_apply_sets_the_stylesheet_and_follows_setting(qapp_theme):
    from classnotes.settings import Settings

    assert theme.apply(qapp_theme, Settings(theme="dark")) == "dark"
    assert DARK["page"] in qapp_theme.styleSheet() and theme.current()["name"] == "dark"
    assert theme.apply(qapp_theme, Settings(theme="light")) == "light"
    assert LIGHT["page"] in qapp_theme.styleSheet()


@pytest.fixture(scope="module")
def qapp_theme():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_buttons_fields_and_speed_control_are_rounded():
    css = qss(LIGHT, pick_fonts({"Segoe UI"}))
    for sel in ('QPushButton#Speed[segment="first"]', 'QPushButton#Speed[segment="last"]', "QLineEdit", "QPlainTextEdit",
                "QAbstractSpinBox", "QComboBox::drop-down", "QDialogButtonBox"):
        assert sel in css
    assert "border-radius: 0;" not in css.replace('QPushButton#Speed[segment="mid"] { border-radius: 0; }', "")


def test_round_popups_makes_menus_and_dropdown_lists_frameless(qapp_theme):
    from PySide6.QtWidgets import QComboBox, QMenu, QWidget

    menu = QMenu()
    host = QWidget()
    combo = QComboBox(host)
    combo.addItems(["Windows default", "Speakers"])
    theme.round_popups(menu, host)
    for w in (menu, combo.view().window()):
        assert w.testAttribute(Qt.WA_TranslucentBackground)
        assert w.windowFlags() & Qt.FramelessWindowHint
