from dataclasses import asdict
import json

from classnotes import store
from classnotes.store import ClassRecord, Segment


def make_record(class_id="2026-11-18", audio="C:/nowhere/class.m4a"):
    return ClassRecord(
        class_id=class_id,
        title="Surah Al-Kahf 1-10",
        date="2026-11-18",
        audio_path=audio,
        duration_s=3725.5,
        models={"asr": "whisper-large-v3", "mt": "nllb"},
        created_at="2026-11-18T19:00:00",
        segments=[
            Segment(0, 12.0, 20.5, "ur", .93, "اس آیت میں", "In this verse"),
            Segment(1, 21.0, 24.0, "en", .97, "What do you think?", "What do you think?"),
            Segment(2, 25.0, 31.0, "ar", .88, "الْحَمْدُ لِلَّهِ", ""),
            Segment(3, 3725.5, 3730.0, "ur", .9, "آخری", "Last", text_edited="The last"),
        ],
    )


def test_roundtrip(tmp_path):
    rec = make_record()
    folder = store.save_record(rec, tmp_path)
    assert store.load_record(folder) == rec


def test_display_text_prefers_edit():
    rec = make_record()
    assert store.display_text(rec.segments[0]) == "In this verse"
    assert store.display_text(rec.segments[3]) == "The last"


def test_save_is_atomic_and_backs_up(tmp_path):
    rec = make_record()
    folder = store.save_record(rec, tmp_path)
    rec.title = "Changed"
    store.save_record(rec, tmp_path, backup=True)
    backups = list(folder.glob("segments.*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text("utf-8"))["title"] == "Surah Al-Kahf 1-10"
    assert not list(folder.glob("*.tmp"))
    assert store.load_record(folder).title == "Changed"


def test_save_without_backup_keeps_no_copy(tmp_path):
    rec = make_record()
    folder = store.save_record(rec, tmp_path)
    store.save_record(rec, tmp_path)
    assert not list(folder.glob("segments.*.json"))


def test_new_class_id_unique(tmp_path):
    assert store.new_class_id(tmp_path, "2026-11-18") == "2026-11-18"
    store.save_record(make_record("2026-11-18"), tmp_path)
    assert store.new_class_id(tmp_path, "2026-11-18") == "2026-11-18-2"
    store.save_record(make_record("2026-11-18-2"), tmp_path)
    assert store.new_class_id(tmp_path, "2026-11-18") == "2026-11-18-3"


def test_load_with_missing_audio(tmp_path):
    folder = store.save_record(make_record(audio="Z:/gone/missing.mp3"), tmp_path)
    assert store.load_record(folder).audio_path == "Z:/gone/missing.mp3"


def test_list_library_skips_corrupt(tmp_path):
    store.save_record(make_record("2026-11-11"), tmp_path)
    newer = make_record("2026-11-18")
    store.save_record(newer, tmp_path)
    bad = tmp_path / "broken"
    bad.mkdir()
    (bad / "segments.json").write_text("{not json", "utf-8")
    ids = [r.class_id for r in store.list_library(tmp_path)]
    assert ids == ["2026-11-18", "2026-11-11"]


def test_list_library_missing_dir(tmp_path):
    assert store.list_library(tmp_path / "nope") == []


def test_notes_md_contains_source_and_edit():
    md = store.render_notes_md(make_record())
    assert md.startswith("# Surah Al-Kahf 1-10")
    assert "**[00:12]** *(Urdu)* In this verse" in md
    assert "> اس آیت میں" in md
    assert "*(English)* What do you think?" in md
    assert "*(Recitation)*" in md and "الْحَمْدُ لِلَّهِ" in md
    assert "**[1:02:05]** *(Urdu)* The last" in md


def test_srt_skips_recitation_and_formats_time():
    srt = store.render_srt(make_record())
    blocks = srt.strip().split("\n\n")
    assert len(blocks) == 3
    assert blocks[0].splitlines()[0] == "1"
    assert blocks[2].splitlines()[0] == "3"
    assert "00:00:12,000 --> 00:00:20,500" in blocks[0]
    assert "01:02:05,500 --> 01:02:10,000" in blocks[2]
    assert "The last" in blocks[2]
    assert "الْحَمْدُ" not in srt


def test_save_retries_when_file_is_briefly_locked(tmp_path, monkeypatch):
    real = store.os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError("locked by another process")
        real(src, dst)

    monkeypatch.setattr(store.os, "replace", flaky)
    monkeypatch.setattr(store, "RETRY_DELAY_S", 0)
    folder = store.save_record(make_record(), tmp_path)
    assert store.load_record(folder) == make_record()


def test_locked_export_does_not_lose_the_class(tmp_path, monkeypatch):
    real = store.os.replace

    def lock_notes(src, dst):
        if str(dst).endswith("notes.md"):
            raise PermissionError("notes.md is open elsewhere")
        real(src, dst)

    monkeypatch.setattr(store.os, "replace", lock_notes)
    monkeypatch.setattr(store, "RETRY_DELAY_S", 0)
    folder = store.save_record(make_record(), tmp_path)
    assert store.load_record(folder) == make_record()
    assert not list(folder.glob("*.tmp"))


def test_locked_segments_file_is_saved_under_another_name(tmp_path, monkeypatch):
    real = store.os.replace

    def lock_segments(src, dst):
        if str(dst).endswith("segments.json"):
            raise PermissionError("segments.json is open elsewhere")
        real(src, dst)

    monkeypatch.setattr(store.os, "replace", lock_segments)
    monkeypatch.setattr(store, "RETRY_DELAY_S", 0)
    import pytest

    with pytest.raises(store.SaveError) as e:
        store.save_record(make_record(), tmp_path)
    saved = list((tmp_path / "2026-11-18").glob("segments.recovered-*.json"))
    assert len(saved) == 1 and saved[0].name in str(e.value)
    assert store.record_from_dict(json.loads(saved[0].read_text("utf-8"))) == make_record()


def test_library_orders_numbered_classes_numerically(tmp_path):
    for cid in ("2026-11-18", "2026-11-18-2", "2026-11-18-10"):
        store.save_record(make_record(class_id=cid), tmp_path)
    assert [r.class_id for r in store.list_library(tmp_path)] == [
        "2026-11-18-10", "2026-11-18-2", "2026-11-18"]


def test_srt_keeps_a_multiline_edit_in_one_block():
    rec = make_record()
    rec.segments = [Segment(0, 1, 2, "ur", .9, "x", "a", text_edited="first line\n\nsecond line"),
                    Segment(1, 3, 4, "en", .9, "b", "b")]
    blocks = store.render_srt(rec).strip().split("\n\n")
    assert len(blocks) == 2
    assert "first line\nsecond line" in blocks[0]


def test_schema1_file_loads_with_new_defaults(tmp_path):
    folder = tmp_path / "c"
    folder.mkdir()
    old = asdict(make_record())
    old["schema_version"] = 1
    for s in old["segments"]:
        for k in ("asr_logprob", "mt_score", "checked"):
            s.pop(k, None)
    (folder / "segments.json").write_text(json.dumps(old, ensure_ascii=False), "utf-8")
    seg = store.load_record(folder).segments[0]
    assert (seg.asr_logprob, seg.mt_score, seg.checked) == (None, None, False)


def test_new_fields_roundtrip_and_schema_is_2(tmp_path):
    rec = make_record()
    rec.segments[0].asr_logprob, rec.segments[0].mt_score, rec.segments[0].checked = -0.42, -0.9, True
    loaded = store.load_record(store.save_record(rec, tmp_path))
    assert loaded == rec and loaded.schema_version == 2
