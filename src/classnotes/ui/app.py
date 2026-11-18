"""Entry point:  uv run classnotes   (or run.bat)"""

from __future__ import annotations

import sys
from pathlib import Path

import classnotes  # noqa: F401  (registers CUDA DLL dirs before ctranslate2 loads)


def ensure_streams(log_path: Path):
    """Under pythonw there is no console: sys.stdout/stderr are None and any print or
    download progress bar would crash. Send them to a log file instead.
    Returns the opened log file, or None if the streams already exist."""
    if sys.stdout is not None and sys.stderr is not None:
        return None
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log
    return log


def main() -> int:
    from .. import paths

    ensure_streams(paths.data_dir() / "classnotes.log")

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
