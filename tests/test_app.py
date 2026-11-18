import sys

from classnotes.ui import app


def test_streams_redirected_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(sys, "stdout", None)
    log = app.ensure_streams(tmp_path / "classnotes.log")
    print("hello")
    sys.stderr.write("progress 50%\n")
    sys.stderr.flush(); sys.stdout.flush()
    assert log is not None
    text = (tmp_path / "classnotes.log").read_text("utf-8")
    assert "hello" in text and "progress 50%" in text


def test_streams_untouched_when_present(tmp_path):
    before = sys.stderr
    assert app.ensure_streams(tmp_path / "x.log") is None
    assert sys.stderr is before
