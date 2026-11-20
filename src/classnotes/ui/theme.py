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
QToolTip { background: $panel; color: $ink; border: 1px solid $line_strong; padding: 4px 8px; }
QMenu { background: $panel; border: 1px solid $line; border-radius: 12px; padding: 8px; }
QMenu::item { padding: 8px 24px 8px 12px; border-radius: 8px; font-size: 15px; }
QMenu::item:selected { background: $surface; }

#Sidebar { background: $page; border-right: 1px solid $line; }
#Brand { font-size: 20px; font-weight: 500; }
#SectionLabel { font-size: 13px; font-weight: 500; color: $muted; }
QLineEdit#Search { background: $panel; border: 1px solid $line_strong; border-radius: 8px;
  padding: 0 12px; min-height: 42px; font-size: 15px; }
QLineEdit#Search:focus { border-color: $accent; }
QListWidget#Classes, QListWidget#Results { background: transparent; border: none; outline: none; }
QListWidget#Classes::item, QListWidget#Results::item { padding: 10px 12px; border-radius: 8px; margin: 2px 0; }
QListWidget#Classes::item:hover, QListWidget#Results::item:hover { background: $surface; }
QListWidget#Classes::item:selected { background: $panel; color: $ink; border: 1px solid $line; }
QListWidget#Results::item:selected { background: $surface; color: $ink; }

#Header { border-bottom: 1px solid $line; }
QLabel#Title { font-size: 26px; font-weight: 500; }
QLabel#Meta { font-size: 13px; color: $muted; }
#Notice, #Banner { background: $panel; border: 1px solid $line; border-radius: 12px; }
#Banner QLabel { color: $flag_label; }

QPushButton { min-height: 42px; padding: 0 20px; border-radius: 8px; font-size: 15px; font-weight: 500; }
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
#Line:hover { background: $hover; }
#Line[playing="true"] { background: $panel; border: 1px solid $line_strong; }
QLabel#Time { font-family: "$mono"; font-size: 13px; color: $muted; }
#Line[playing="true"] QLabel#Time { color: $accent; }
QLabel#Lang, QLabel#Tag { font-size: 13px; color: $muted; }
QLabel#English { font-size: 17px; }
QLabel#Urdu { font-family: "$urdu"; font-size: 19px; color: $urdu; }
QLabel#Arabic { font-family: "$arabic"; font-size: 22px; color: $urdu; }
QLabel#FlagLabel { font-size: 13px; font-weight: 500; color: $flag_label; }
QLabel#Empty { font-size: 16px; color: $muted; }
QPlainTextEdit#Editor { background: $panel; border: 1px solid $accent; border-radius: 8px; padding: 8px;
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
QPushButton#Speed { min-height: 34px; padding: 0 10px; font-family: "$mono"; font-size: 13px;
  border: 1px solid $line_strong; border-radius: 0; background: $panel; }
QPushButton#Speed:checked { background: $ink; color: $page; border-color: $ink; }
QLabel#Clock { font-family: "$mono"; font-size: 13px; color: $muted; }
QLabel#Key { font-family: "$mono"; font-size: 12px; color: $muted; border: 1px solid $line;
  border-radius: 6px; padding: 2px 6px; }
QComboBox { background: $panel; border: 1px solid $line_strong; border-radius: 8px; padding: 0 10px;
  min-height: 34px; font-size: 13px; }
QComboBox QAbstractItemView { background: $panel; border: 1px solid $line; selection-background-color: $surface;
  selection-color: $ink; }
QProgressBar { background: $surface; border: none; border-radius: 3px; max-height: 6px; }
QProgressBar::chunk { background: $accent; border-radius: 3px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: $line_strong; border-radius: 5px; min-height: 40px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
""")


def qss(tokens: dict[str, str], fonts: dict[str, str]) -> str:
    return _QSS.substitute({**tokens, **fonts})


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
