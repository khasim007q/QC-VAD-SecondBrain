from classnotes.search import SearchIndex, normalize
from classnotes.store import Segment

from test_store import make_record


def index_with(*segs, title="Class one"):
    rec = make_record()
    rec.title = title
    rec.segments = list(segs)
    return SearchIndex([rec])


def S(i, source, text, **kw):
    return Segment(i, i * 10.0, i * 10.0 + 5, "ur", 0.99, source, text, **kw)


def test_finds_english_edit_and_urdu():
    idx = index_with(S(0, "اپنی سنتوں کے ذریعے", "through his saints", text_edited="through his Sunnah"),
                     S(1, "اس آیت میں", "In this verse"))
    assert [h.seg_id for h in idx.search("Sunnah")] == [0]
    assert [h.seg_id for h in idx.search("سنتوں")] == [0]
    assert [h.seg_id for h in idx.search("saints")] == [0]  # machine text is searched too


def test_urdu_vowel_marks_are_ignored():
    idx = index_with(S(0, "حضرتِ ابوبکر آئے", "Hazrat Abu Bakr came"))
    assert [h.seg_id for h in idx.search("حضرت")] == [0]
    assert normalize("حضرتِ") == "حضرت"


def test_case_insensitive_english():
    idx = index_with(S(0, "ہجرت", "The Hijrat began"))
    assert len(idx.search("hijrat")) == 1


def test_title_match_returns_a_title_hit():
    hits = index_with(S(0, "x", "y"), title="Session 19 · Hijrat e Rasool (SAW)").search("hijrat")
    assert [h.seg_id for h in hits] == [-1]


def test_short_or_mark_only_queries_return_nothing():
    idx = index_with(S(0, "حضرتِ ابوبکر", "a b c"))
    assert idx.search("a") == [] and idx.search("ِ") == [] and idx.search("   ") == []


def test_regex_characters_are_literal():
    idx = index_with(S(0, "رسول اللہ", "Rasulullah (SAW) said"))
    assert len(idx.search("(SAW)")) == 1
    assert idx.search("*") == [] and idx.search("[") == [] and idx.search("(.*") == []


def test_snippet_bounds_the_match():
    long = "word " * 60 + "Sunnah " + "word " * 60
    hit = index_with(S(0, "x", long)).search("sunnah")[0]
    assert len(hit.snippet) <= 120
    assert normalize(hit.snippet[hit.match_start:hit.match_end]) == "sunnah"


def test_snippet_maps_back_through_vowel_marks():
    hit = index_with(S(0, "پھر حضرتِ ابوبکر آئے", "z")).search("ابوبکر")[0]
    assert hit.snippet[hit.match_start:hit.match_end] == "ابوبکر"
