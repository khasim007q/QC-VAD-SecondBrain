"""Light and dark themes: colour tokens, a contrast check, the stylesheet, and system fonts.

Every colour on screen comes from LIGHT or DARK (drafts A and B in docs/design/drafts). Widgets are
styled by object name (and the `kind` / `playing` / `flagged` properties) in one QSS template.
"""

from __future__ import annotations

from string import Template

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

LIGHT = {
    "page": "#f8f8f8", "surface": "#eeeeee", "panel": "#ffffff", "ink": "#0a0a0a",
    "accent": "#1f6b3a", "accent_hover": "#1b5c32", "accent_label": "#ffffff", "muted": "#5b5f5c",
    "urdu": "#3b3e3c", "line": "rgba(10, 10, 10, 33)", "line_strong": "rgba(10, 10, 10, 71)",
    "hover": "#f1f1f1", "flag_dot": "#b26b00", "flag_label": "#7a4b00",
}
DARK = {
    "page": "#161c1a", "surface": "#1f2725", "panel": "#26302d", "ink": "#e3e2da",
    "accent": "#9fc7b8", "accent_hover": "#b6d6ca", "accent_label": "#13201b", "muted": "#a3a89f",
    "urdu": "#cfcdc4", "line": "rgba(227, 226, 218, 31)", "line_strong": "rgba(227, 226, 218, 66)",
    "hover": "#1c2321", "flag_dot": "#e0a84f", "flag_label": "#e8bd73",
}

# First installed family wins. Nastaliq for Urdu when Windows has it (optional "Urdu supplemental
# fonts"), else Segoe UI, which covers Urdu and Arabic in naskh style.
FONT_CHOICES = {
    "ui": ("Segoe UI Variable Text", "Segoe UI"),
    "mono": ("Cascadia Mono", "Consolas"),
    "urdu": ("Urdu Typesetting", "Jameel Noori Nastaleeq", "Segoe UI"),
    "arabic": ("Sakkal Majalla", "Traditional Arabic", "Segoe UI"),
}
FALLBACK = {"ui": "Segoe UI", "mono": "Consolas", "urdu": "Segoe UI", "arabic": "Segoe UI"}

_current: dict = {"name": "light", "tokens": LIGHT, "fonts": dict(FALLBACK)}


def _luminance(hex_colour: str) -> float:
    c = QColor(hex_colour)

    def ch(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * ch(c.redF()) + 0.7152 * ch(c.greenF()) + 0.0722 * ch(c.blueF())


def contrast(fg: str, bg: str) -> float:
    """WCAG contrast ratio between two opaque colours."""
    a, b = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def resolve(setting: str, scheme: Qt.ColorScheme) -> str:
    if setting in ("light", "dark"):
        return setting
    return "dark" if scheme == Qt.ColorScheme.Dark else "light"


def pick_fonts(available: set[str]) -> dict[str, str]:
    return {k: next((f for f in names if f in available), FALLBACK[k]) for k, names in FONT_CHOICES.items()}


_QSS = Template("""
* { font-family: "$ui"; color: $ink; }
QMainWindow, QDialog, #Main { background: $page; }
QToolTip { background: $panel; color: $ink; border: 1px solid $line_strong; border-radius: 8px; padding: 6px 10px; }
QMenu { background: $panel; border: 1px solid $line_strong; border-radius: 14px; padding: 6px; }
QMenu::item { padding: 9px 28px 9px 12px; border-radius: 10px; font-size: 15px; }
QMenu::item:selected { background: $surface; }
QMenu::separator { height: 1px; background: $line; margin: 6px 8px; }
QComboBoxPrivateContainer { background: transparent; border: none; }

#Sidebar { background: $page; border-right: 1px solid $line; }
#Brand { font-size: 20px; font-weight: 500; }
#SectionLabel { font-size: 13px; font-weight: 500; color: $muted; }
QLineEdit#Search { background: $panel; border: 1px solid $line_strong; border-radius: 12px;
  padding: 0 12px; min-height: 42px; font-size: 15px; }
QLineEdit#Search:focus { border-color: $accent; }
QListWidget#Classes, QListWidget#Results { background: transparent; border: none; outline: none; }
QListWidget#Classes, QListWidget#Results { font-size: 14px; }
QListWidget#Classes::item, QListWidget#Results::item { padding: 10px 12px; border-radius: 12px; margin: 2px 0; }
QListWidget#Classes::item:hover, QListWidget#Results::item:hover { background: $surface; }
QListWidget#Classes::item:selected { background: $panel; color: $ink; border: 1px solid $line; }
QListWidget#Results::item:selected { background: $surface; color: $ink; }

#Header { border-bottom: 1px solid $line; }
QLabel#Title { font-size: 26px; font-weight: 500; }
QLabel#Meta { font-size: 13px; color: $muted; }
#Notice, #Banner { background: $panel; border: 1px solid $line; border-radius: 12px; }
#Banner QLabel { color: $flag_label; }

QPushButton { min-height: 42px; padding: 0 20px; border-radius: 12px; font-size: 15px; font-weight: 500; }
QPushButton[kind="secondary"], QPushButton:!flat { background: $panel; border: 1px solid $line_strong; }
QPushButton[kind="secondary"]:hover { border-color: $ink; background: $surface; }
QPushButton[kind="primary"] { background: $accent; border: 1px solid $accent; color: $accent_label; }
QPushButton[kind="primary"]:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton[kind="link"] { background: transparent; border: none; color: $accent; padding: 0; min-height: 24px;
  font-size: 14px; text-align: left; }
QPushButton[kind="link"]:hover { text-decoration: underline; }
QPushButton:disabled { color: $muted; border-color: $line; }
QPushButton:focus { outline: none; border: 2px solid $accent; }
QPushButton::menu-indicator { width: 0; }

#LineList, #LineList > QWidget > QWidget#LineHost { background: $page; border: none; }
#Line { background: transparent; border: 1px solid transparent; border-radius: 12px; }
QLabel#Time { font-family: "$mono"; font-size: 13px; color: $muted; }
QLabel#Lang, QLabel#Tag { font-size: 13px; color: $muted; }
QLabel#English { font-size: 17px; }
QLabel#Urdu { font-family: "$urdu"; font-size: 19px; color: $urdu; }
QLabel#Arabic { font-family: "$arabic"; font-size: 22px; color: $urdu; }
QLabel#FlagLabel { font-size: 13px; font-weight: 500; color: $flag_label; }
QLabel#Empty { font-size: 16px; color: $muted; }
QPlainTextEdit#Editor { background: $panel; border: 1px solid $accent; border-radius: 12px; padding: 8px;
  font-size: 17px; selection-background-color: $accent; selection-color: $accent_label; }
QLabel#Hint { font-size: 13px; color: $muted; }

#PlayerBar { background: $panel; border-top: 1px solid $line; }
QPushButton#Icon { min-width: 40px; max-width: 40px; min-height: 40px; max-height: 40px; padding: 0;
  border: none; border-radius: 20px; background: transparent; }
QPushButton#Icon:hover { background: $surface; }
QPushButton#Icon:checked { background: $surface; border: 1px solid $line_strong; }
QPushButton#Play { min-width: 48px; max-width: 48px; min-height: 48px; max-height: 48px; padding: 0;
  border-radius: 24px; background: $accent; border: none; }
QPushButton#Play:hover { background: $accent_hover; }
QPushButton#Speed { min-height: 34px; min-width: 52px; padding: 0 4px; font-family: "$mono"; font-size: 13px;
  border: 1px solid $line_strong; background: $panel; }
QPushButton#Speed[segment="mid"] { border-radius: 0; }
QPushButton#Speed[segment="mid"], QPushButton#Speed[segment="last"] { border-left: none; }
QPushButton#Speed[segment="first"] { border-top-left-radius: 12px; border-bottom-left-radius: 12px;
  border-top-right-radius: 0px; border-bottom-right-radius: 0px; }
QPushButton#Speed[segment="last"] { border-top-right-radius: 12px; border-bottom-right-radius: 12px;
  border-top-left-radius: 0px; border-bottom-left-radius: 0px; }
QPushButton#Speed:hover { background: $surface; }
QPushButton#Speed:checked { background: $ink; color: $page; border-color: $ink; }
QLabel#Clock { font-family: "$mono"; font-size: 13px; color: $muted; }
QLabel#Key { font-family: "$mono"; font-size: 12px; color: $muted; border: 1px solid $line;
  border-radius: 6px; padding: 2px 6px; }
QComboBox { background: $panel; border: 1px solid $line_strong; border-radius: 12px; padding: 0 12px;
  min-height: 40px; font-size: 14px; }
QComboBox:hover { border-color: $ink; }
QComboBox:focus { border-color: $accent; }
QComboBox::drop-down { border: none; width: 30px; subcontrol-origin: padding; subcontrol-position: center right; }
QComboBox::down-arrow { image: url("$chevron_down"); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: $panel; border: 1px solid $line_strong; border-radius: 12px; padding: 6px;
  outline: none; selection-background-color: $surface; selection-color: $ink; }
QComboBox QAbstractItemView::item { min-height: 34px; padding: 0 10px; border-radius: 8px; }

QLineEdit, QPlainTextEdit, QAbstractSpinBox { background: $panel; border: 1px solid $line_strong; border-radius: 12px;
  padding: 6px 12px; font-size: 14px; selection-background-color: $accent; selection-color: $accent_label; }
QLineEdit, QAbstractSpinBox { min-height: 28px; }
QLineEdit:focus, QPlainTextEdit:focus, QAbstractSpinBox:focus { border-color: $accent; }
QLineEdit:read-only { background: $surface; }
QAbstractSpinBox QLineEdit { border: none; background: transparent; padding: 0; min-height: 0; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { width: 24px; border: none; background: transparent; }
QAbstractSpinBox::up-arrow { image: url("$chevron_up"); width: 10px; height: 10px; }
QAbstractSpinBox::down-arrow { image: url("$chevron_down"); width: 10px; height: 10px; }
QDialog QLabel { font-size: 14px; }
QDialog QScrollArea, #SettingsBody { background: $page; border: none; }
QDialogButtonBox QPushButton { min-width: 100px; }
QProgressBar { background: $surface; border: none; border-radius: 3px; max-height: 6px; }
QProgressBar::chunk { background: $accent; border-radius: 3px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: $line_strong; border-radius: 5px; min-height: 40px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
""")


_CHEVRON = ('<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
            '<path d="{d}" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" '
            'stroke-linejoin="round"/></svg>')


def chevrons(tokens: dict[str, str]) -> dict[str, str]:
    """Small arrow images in the theme's muted colour, for dropdowns and number boxes. Written
    once per colour to the app data folder; returns QSS-ready paths."""
    from .. import paths

    folder = paths.data_dir() / "theme"
    folder.mkdir(parents=True, exist_ok=True)
    colour = tokens["muted"]
    out = {}
    for key, d in (("chevron_down", "M2.5 4.5 6 8l3.5-3.5"), ("chevron_up", "M2.5 7.5 6 4l3.5 3.5")):
        f = folder / f"{key}-{colour.lstrip('#')}.svg"
        if not f.exists():
            f.write_text(_CHEVRON.format(d=d, c=colour), "utf-8")
        out[key] = f.as_posix()
    return out


def qss(tokens: dict[str, str], fonts: dict[str, str]) -> str:
    return _QSS.substitute({**tokens, **fonts, **chevrons(tokens)})


def palette(tokens: dict[str, str]) -> QPalette:
    p = QPalette()
    roles = {
        QPalette.Window: "page", QPalette.Base: "panel", QPalette.AlternateBase: "surface",
        QPalette.Text: "ink", QPalette.WindowText: "ink", QPalette.Button: "panel",
        QPalette.ButtonText: "ink", QPalette.Highlight: "accent", QPalette.HighlightedText: "accent_label",
        QPalette.PlaceholderText: "muted", QPalette.ToolTipBase: "panel", QPalette.ToolTipText: "ink",
        QPalette.Link: "accent",
    }
    for role, key in roles.items():
        p.setColor(role, QColor(tokens[key]))
    return p


def _round_window(w) -> None:
    if not w.testAttribute(Qt.WA_TranslucentBackground):
        w.setWindowFlags(w.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        w.setAttribute(Qt.WA_TranslucentBackground)


def round_popups(*widgets) -> None:
    """Menus and dropdown lists open in windows of their own. Make those frameless and see-through
    so the stylesheet's rounded corners show, not a square window behind them. Pass menus, combo
    boxes, or any widget whose child combo boxes should be done."""
    from PySide6.QtWidgets import QComboBox, QMenu

    for w in widgets:
        if isinstance(w, QMenu):
            _round_window(w)
            continue
        combos = [w] if isinstance(w, QComboBox) else w.findChildren(QComboBox)
        for c in combos:
            _round_window(c.view().window())  # view() creates the popup's container window


def load_fonts() -> dict[str, str]:
    from PySide6.QtGui import QFontDatabase

    return pick_fonts(set(QFontDatabase.families()))


def apply(app, settings) -> str:
    """Style the whole application for the theme the settings ask for. Returns "light"/"dark"."""
    name = resolve(settings.theme, app.styleHints().colorScheme())
    tokens = DARK if name == "dark" else LIGHT
    fonts = load_fonts()
    _current.update(name=name, tokens=tokens, fonts=fonts)
    app.setPalette(palette(tokens))
    app.setStyleSheet(qss(tokens, fonts))
    return name


def current() -> dict:
    """The tokens and fonts last applied: {"name", "tokens", "fonts"} (for painted widgets)."""
    return _current
