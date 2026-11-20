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


def test_split_keeps_decimals_abbreviations_and_urls_together():
    text = "Dr. Israr said 3.5 percent, e.g. at www.example.com today. Next one"
    assert split_sentences([text]) == [
        "Dr. Israr said 3.5 percent, e.g. at www.example.com today.", "Next one"]


def test_split_still_splits_urdu_and_normal_sentences():
    assert split_sentences(["یہ پہلا ہے۔ یہ دوسرا ہے؟ End. Start"]) == [
        "یہ پہلا ہے۔", "یہ دوسرا ہے؟", "End.", "Start"]


def test_term_absorbs_a_following_vowel_mark():
    terms = parse_terms("حضرت = Hazrat")
    assert apply_terms("حضرتِ ابوبکر", terms) == "Hazrat ابوبکر"


def test_replacements_do_not_chain():
    terms = parse_terms("خریب = قریب\nقریب = near")
    assert apply_terms("خریب", terms) == "قریب"
    assert apply_terms("قریب", terms) == "near"


def test_default_terms_cover_the_aalihi_salutation():
    terms = parse_terms(DEFAULT_TERMS)
    assert apply_terms("رسول اللہ صلی اللہ علیہ وآلہ وسلم نے", terms) == "Rasulullah (SAW) نے"


def test_zuhr_misheard_as_poison_is_fixed_when_the_segment_is_about_prayer():
    from classnotes.translate import apply_context_fixes

    seg = "جمعے میں دو ہی رکاتیں کیوں ہیں؟ زہر میں تو چار ہوتی ہیں"
    assert apply_context_fixes("زہر میں تو چار ہوتی ہیں", seg) == "ظہر میں تو چار ہوتی ہیں"


def test_poison_stays_poison_without_prayer_context():
    from classnotes.translate import apply_context_fixes

    seg = "سانپ کا زہر بہت خطرناک تھا اور زہریلے جانور"
    assert apply_context_fixes(seg, seg) == seg
