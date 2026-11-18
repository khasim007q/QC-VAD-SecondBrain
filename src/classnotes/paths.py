"""Where the app keeps models, settings and the class library."""

from pathlib import Path

from platformdirs import user_data_dir, user_documents_dir

APP_NAME = "ClassNotes"


def data_dir() -> Path:
    d = Path(user_data_dir(APP_NAME, appauthor=False))
    d.mkdir(parents=True, exist_ok=True)
    return d


def models_dir() -> Path:
    d = data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_library_dir() -> Path:
    return Path(user_documents_dir()) / APP_NAME
