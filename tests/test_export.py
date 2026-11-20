import csv
import io
import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from classnotes import export, store  # noqa: E402

from test_store import make_record  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_formats_are_the_eight_from_the_design():
    assert export.FORMATS == [
        ("md", "Notes", ".md"), ("docx", "Word document", ".docx"), ("pdf", "PDF", ".pdf"),
        ("srt", "Subtitles", ".srt"), ("vtt", "Web subtitles", ".vtt"), ("txt", "Plain text", ".txt"),
        ("csv", "Spreadsheet", ".csv"), ("json", "Data for search tools", ".json")]


@pytest.mark.parametrize("kind", [k for k, _, _ in export.FORMATS])
def test_every_format_writes_a_file(qapp, tmp_path, kind):
    path = tmp_path / f"out.{kind}"
    export.export(make_record(), kind, path)
    assert path.is_file() and path.stat().st_size > 0


def test_md_matches_notes(tmp_path):
    rec = make_record()
    export.export(rec, "md", tmp_path / "n.md")
    assert (tmp_path / "n.md").read_text("utf-8") == store.render_notes_md(rec)


def test_docx_has_edit_and_rtl_urdu(tmp_path):
    import docx

    export.export(make_record(), "docx", tmp_path / "n.docx")
    d = docx.Document(str(tmp_path / "n.docx"))
    texts = [p.text for p in d.paragraphs]
    assert any("The last" in t for t in texts) and any("آخری" in t for t in texts)
    urdu = next(p for p in d.paragraphs if "آخری" in p.text)
    assert urdu._p.pPr is not None and urdu._p.pPr.find(docx.oxml.ns.qn("w:bidi")) is not None


def test_pdf_is_a_pdf(qapp, tmp_path):
    export.export(make_record(), "pdf", tmp_path / "n.pdf")
    assert (tmp_path / "n.pdf").read_bytes()[:4] == b"%PDF"


def test_csv_has_bom_header_and_rows(tmp_path):
    export.export(make_record(), "csv", tmp_path / "n.csv")
    raw = (tmp_path / "n.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    assert rows[0] == ["start", "end", "language", "urdu", "english_machine", "english_edited", "flag"]
    assert len(rows) == 5 and rows[4][5] == "The last"


def test_vtt_cues(tmp_path):
    export.export(make_record(), "vtt", tmp_path / "n.vtt")
    text = (tmp_path / "n.vtt").read_text("utf-8")
    assert text.startswith("WEBVTT") and "00:00:12.000 --> 00:00:20.500" in text


def test_txt_lines(tmp_path):
    export.export(make_record(), "txt", tmp_path / "n.txt")
    lines = (tmp_path / "n.txt").read_text("utf-8").splitlines()
    assert "[00:12] In this verse" in lines
    assert any(ln.startswith("[00:25] (Recitation)") for ln in lines)
    assert "[1:02:05] The last" in lines


def test_json_round_trips(tmp_path):
    rec = make_record()
    export.export(rec, "json", tmp_path / "n.json")
    assert store.record_from_dict(json.loads((tmp_path / "n.json").read_text("utf-8"))) == rec


@pytest.mark.parametrize("kind", [k for k, _, _ in export.FORMATS])
def test_empty_class_exports_valid_files(qapp, tmp_path, kind):
    rec = make_record()
    rec.segments = []
    path = tmp_path / f"e.{kind}"
    export.export(rec, kind, path)
    assert path.is_file()
    if kind == "json":
        assert json.loads(path.read_text("utf-8"))["segments"] == []
    if kind == "csv":
        assert len(list(csv.reader(io.StringIO(path.read_text("utf-8-sig"))))) == 1


def test_default_name_strips_forbidden_characters():
    rec = make_record()
    rec.title = 'Al-Kahf: 1/10 "intro"?'
    assert export.default_name(rec, ".md") == "2026-11-18 Al-Kahf 110 intro.md"
