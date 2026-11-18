"""Entry point:  uv run classnotes   (or run.bat)"""

from __future__ import annotations

import sys

import classnotes  # noqa: F401  (registers CUDA DLL dirs before ctranslate2 loads)


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Class Notes")
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
