import pytest

from classnotes.segment import LangSpan, bucket_probs, choose_lang, merge_spans

SR = 16000


def test_bucket_sums_hindi_into_urdu():
    b = bucket_probs([("ur", .3), ("hi", .4), ("en", .2), ("ar", .05), ("fr", .05)])
    assert set(b) == {"ur", "en", "ar"}
    assert b["ur"] == pytest.approx(.7)
    assert b["en"] == pytest.approx(.2)
    assert b["ar"] == pytest.approx(.05)


def test_choose_english_when_confident():
    lang, conf = choose_lang({"ur": .1, "en": .9, "ar": 0}, 3 * SR)
    assert lang == "en"
    assert conf == pytest.approx(.9, abs=1e-6)


def test_choose_arabic():
    assert choose_lang({"ur": .1, "en": .05, "ar": .85}, 5 * SR)[0] == "ar"


def test_short_span_defaults_to_urdu():
    assert choose_lang({"ur": .05, "en": .95, "ar": 0}, 1 * SR)[0] == "ur"


def test_low_confidence_defaults_to_urdu():
    assert choose_lang({"ur": .4, "en": .6, "ar": 0}, 5 * SR)[0] == "ur"


def _s(a, b, lang="ur", conf=.9):
    return LangSpan(int(a * SR), int(b * SR), lang, conf)


def test_merge_same_lang_small_gap():
    out = merge_spans([_s(0, 4, conf=.9), _s(4.5, 8, conf=.8)])
    assert len(out) == 1
    assert (out[0].start, out[0].end) == (0, 8 * SR)
    assert out[0].conf == pytest.approx(.8)


def test_no_merge_across_language():
    assert len(merge_spans([_s(0, 4, "ur"), _s(4.5, 8, "en")])) == 2


def test_no_merge_big_gap():
    assert len(merge_spans([_s(0, 4), _s(5.5, 8)])) == 2


def test_no_merge_over_max_len():
    assert len(merge_spans([_s(0, 15), _s(15.5, 30.5)])) == 2


def test_merge_empty():
    assert merge_spans([]) == []
