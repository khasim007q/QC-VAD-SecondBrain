from classnotes import flags
from classnotes.store import Segment

URDU = "یہ ایک لمبا جملہ ہے جس میں بہت سارے الفاظ ہیں تاکہ تناسب ٹھیک رہے"  # 15 words


def seg(i=0, lang="ur", conf=0.99, source=URDU, text="This is a long sentence with a lot of words so the ratio holds.",
        **kw):
    return Segment(i, i * 10.0, i * 10.0 + 5, lang, conf, source, text, **kw)


def test_clean_line_is_not_flagged():
    assert flags.flag_reason(seg()) is None


def test_language_unsure():
    assert flags.flag_reason(seg(conf=flags.MIN_LANG_CONF - 0.01)) == "Language unsure"


def test_very_short():
    assert flags.flag_reason(seg(source="ہے", text="It is.")) == "Very short, may be noise"


def test_translation_missing_words():
    assert flags.flag_reason(seg(text="Yes.")) == "Translation may be missing words"


def test_misheard():
    assert flags.flag_reason(seg(asr_logprob=flags.MIN_ASR_LOGPROB - 0.01)) == "Words may be misheard"


def test_translation_unsure():
    assert flags.flag_reason(seg(mt_score=flags.MIN_MT_SCORE - 0.01)) == "Translation unsure"


def test_first_reason_wins():
    s = seg(conf=0.1, source="ہے", text="It is.")
    assert flags.flag_reason(s) == "Language unsure"


def test_edited_checked_and_recitation_are_never_flagged():
    assert flags.flag_reason(seg(conf=0.1, text_edited="Fixed.")) is None
    assert flags.flag_reason(seg(conf=0.1, checked=True)) is None
    assert flags.flag_reason(seg(lang="ar", conf=0.1, source="الحمد", text="")) is None


def test_word_ratio_applies_to_urdu_only():
    assert flags.flag_reason(seg(lang="en", source=URDU, text="Yes.")) is None


def test_none_scores_are_ignored():
    assert flags.flag_reason(seg(asr_logprob=None, mt_score=None)) is None


def test_flagged_ids_and_next_flagged_wraps_round():
    segs = [seg(1), seg(3, conf=0.1), seg(5), seg(7, conf=0.1)]
    assert flags.flagged_ids(segs) == [3, 7]
    assert flags.next_flagged(segs, None) == 3
    assert flags.next_flagged(segs, 3) == 7
    assert flags.next_flagged(segs, 7) == 3
    assert flags.next_flagged(segs, 4) == 7
    assert flags.next_flagged([seg(1)], None) is None
