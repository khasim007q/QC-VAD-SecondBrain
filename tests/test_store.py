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
