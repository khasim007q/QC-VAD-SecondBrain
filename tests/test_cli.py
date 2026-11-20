import io
import sys

from classnotes import cli


def test_cli_output_survives_a_non_utf8_console(monkeypatch):
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252"))
    cli._utf8_streams()
    print("[00:01] (ur) رسول اللہ")
    sys.stdout.flush()
    assert "رسول".encode("utf-8") in raw.getvalue()


def test_cli_rejects_a_malformed_date(tmp_path):
    import pytest

    with pytest.raises(SystemExit) as e:
        cli.main([str(tmp_path / "a.mp3"), "--date", "2026/11/18", "--library", str(tmp_path)])
    assert e.value.code == 2
    assert not (tmp_path / "2026").exists()


def test_cli_reprocess_unknown_class_fails_before_decoding(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "load_audio", lambda p: (_ for _ in ()).throw(AssertionError("decoded")))
    assert cli.main([str(tmp_path / "a.mp3"), "--reprocess", "nope", "--library", str(tmp_path)]) == 1
    assert "nope" in capsys.readouterr().err
