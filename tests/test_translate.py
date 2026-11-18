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
