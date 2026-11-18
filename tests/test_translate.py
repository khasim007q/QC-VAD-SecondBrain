from classnotes.translate import split_sentences


def test_split_on_urdu_marks():
    out = split_sentences(["پہلا جملہ۔ دوسرا؟ third one."])
    assert out == ["پہلا جملہ۔", "دوسرا؟", "third one."]


def test_split_across_whisper_segments():
    assert split_sentences(["ایک۔", "دو"]) == ["ایک۔", "دو"]


def test_split_long_unpunctuated():
    words = [f"لفظ{i}" for i in range(200)]
    text = " ".join(words)
    assert len(text) > 1000
    out = split_sentences([text])
    assert all(len(p) <= 300 for p in out)
    assert " ".join(out).split() == words


def test_split_prefers_comma_for_long_pieces():
    a = "الف " * 30  # ~120 chars
    b = "ب " * 50  # ~100 chars
    out = split_sentences([a.strip() + "، " + b.strip()], max_chars=150)
    assert out[0].endswith("،")
    assert all(len(p) <= 150 for p in out)


def test_split_drops_empty():
    assert split_sentences(["  ", "۔"]) == []


from classnotes.translate import DEFAULT_TERMS, apply_terms, parse_terms


def test_parse_terms_skips_comments_and_sorts_longest_first():
    terms = parse_terms("# comment\n\nحضرت = Hazrat\nنعوذ باللہ = (God forbid)\nbad line\n")
    assert terms == [("نعوذ باللہ", "(God forbid)"), ("حضرت", "Hazrat")]


def test_apply_terms_whole_words_only():
    terms = parse_terms("خریب = قریب")
    assert apply_terms("خدا کے خریب ہونا", terms) == "خدا کے قریب ہونا"
    assert apply_terms("خریبی", terms) == "خریبی"


def test_apply_terms_multiword_and_punctuation():
    terms = parse_terms("حضرت = Hazrat\nنعوذ باللہ = (God forbid)")
    assert apply_terms("کہ نعوذ باللہ، حضرت عمر۔", terms) == "کہ (God forbid)، Hazrat عمر۔"


def test_default_terms_cover_known_mishearings():
    terms = dict(parse_terms(DEFAULT_TERMS))
    for wrong in ["حضرت", "حجرت", "مشرقین", "ختل", "خریب", "خوریش", "نوزباللہ", "ظہر", "ﷺ"]:
        assert wrong in terms


def test_default_terms_rasulullah_phrase_wins_over_symbol():
    terms = parse_terms(DEFAULT_TERMS)
    out = apply_terms("رسول اللہ ﷺ کے گھر کو گھیرا اور آپ ﷺ نکلے", terms)
    assert out == "Rasulullah (SAW) کے گھر کو گھیرا اور آپ (SAW) نکلے"
