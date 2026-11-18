import numpy as np

from classnotes.pipeline import run_pipeline
from classnotes.settings import Settings

SR = 16000

PROBS = {
    "ur": [("ur", .5), ("hi", .4), ("en", .1)],
    "en": [("en", .95), ("ur", .05)],
    "ar": [("ar", .9), ("ur", .1)],
}


class FakeAsr:
    """Spans given in seconds with a scripted language and transcript."""

    def __init__(self, spans):
        self.spans = spans  # list of (start_s, end_s, lang, [texts])
        self.prompts = []

    def speech_spans(self, audio):
        return [(int(a * SR), int(b * SR)) for a, b, _, _ in self.spans]

    def lang_probs(self, clip):
        return PROBS[self.spans[int(clip[0])][2]]

    def transcribe(self, clip, lang, prompt):
        self.prompts.append((lang, prompt))
        # merged spans start with the first span's marker; return all covered texts
        first = int(clip[0])
        last = int(clip[-1])
        return [t for i in range(first, last + 1) for t in self.spans[i][3]]


class FakeTranslator:
    def __init__(self):
        self.seen = []

    def translate(self, sentences):
        self.seen.extend(sentences)
        return ["EN:" + s for s in sentences]


def make_audio(spans, total_s=60):
    """Fill each span's samples with its index so the fake can tell spans apart."""
    audio = np.full(int(total_s * SR), -1.0, dtype=np.float32)
    for i, (a, b, _, _) in enumerate(spans):
        audio[int(a * SR):int(b * SR)] = i
    return audio


def run(spans, cancel_after=None, settings=None):
    asr, tr = FakeAsr(spans), FakeTranslator()
    got, progress = [], []

    def cancelled():
        return cancel_after is not None and len(got) >= cancel_after

    result = run_pipeline(make_audio(spans), asr, tr, settings or Settings(),
                          on_segment=got.append,
                          on_progress=lambda stage, f: progress.append((stage, f)),
                          cancelled=cancelled)
    return result, got, progress, asr, tr


def test_pipeline_routes_by_language():
    spans = [
        (0, 5, "ur", ["اس آیت میں۔"]),
        (10, 14, "en", ["What do you think it means?"]),
        (20, 26, "ar", ["الحمد لله رب العالمين"]),
    ]
    result, got, _, asr, tr = run(spans)
    assert [s.lang for s in result] == ["ur", "en", "ar"]
    ur, en, ar = result
    assert ur.source == "اس آیت میں۔" and ur.text == "EN:اس آیت میں۔"
    assert en.source == en.text == "What do you think it means?"
    assert ar.source == "الحمد لله رب العالمين" and ar.text == ""
    assert tr.seen == ["اس آیت میں۔"]  # Arabic and English never translated
    assert (ur.start, ur.end) == (0.0, 5.0)
    assert [s.id for s in result] == [0, 1, 2]
    assert got == result
    assert dict(asr.prompts)["ar"] is None
    assert dict(asr.prompts)["ur"] == Settings().glossary


def test_pipeline_no_speech():
    result, got, progress, _, _ = run([])
    assert result == [] and got == []
    assert progress[-1][1] == 1.0


def test_pipeline_skips_empty_text():
    spans = [(0, 5, "en", ["  "]), (10, 15, "en", ["Hello class."])]
    result, *_ = run(spans)
    assert [s.source for s in result] == ["Hello class."]
    assert result[0].id == 0


def test_pipeline_cancel():
    spans = [(0, 5, "en", ["One."]), (10, 15, "en", ["Two."]), (20, 25, "en", ["Three."])]
    result, got, *_ = run(spans, cancel_after=1)
    assert result is None
    assert len(got) == 1


def test_pipeline_merges_neighbours():
    spans = [(0, 5, "ur", ["پہلا۔"]), (5.5, 9, "ur", ["دوسرا۔"])]
    result, *_ = run(spans)
    assert len(result) == 1
    assert (result[0].start, result[0].end) == (0.0, 9.0)
    assert result[0].text == "EN:پہلا۔ EN:دوسرا۔"


def test_pipeline_progress_monotonic_and_complete():
    spans = [(0, 5, "en", ["A."]), (10, 15, "ur", ["ب۔"])]
    _, _, progress, *_ = run(spans)
    fr = [f for stage, f in progress if stage == "Transcribing"]
    assert fr == sorted(fr) and fr[-1] == 1.0


def _process(tmp_path, spans, class_id=None, cancel=False):
    from classnotes.pipeline import process_recording
    return process_recording(
        make_audio(spans), audio_path="C:/rec/class.m4a", title="T", date="2026-11-18",
        library=tmp_path, asr=FakeAsr(spans), translator=FakeTranslator(), settings=Settings(),
        on_segment=lambda s: None, on_progress=lambda *a: None,
        cancelled=lambda: cancel, class_id=class_id,
    )


def test_process_recording_saves_record(tmp_path):
    from classnotes import store
    rec = _process(tmp_path, [(0, 5, "en", ["Hello."])])
    assert rec.class_id == "2026-11-18"
    assert rec.duration_s == 60.0
    assert rec.models["asr"] == "whisper-large-v3"
    loaded = store.load_record(tmp_path / "2026-11-18")
    assert loaded.segments[0].text == "Hello."


def test_process_recording_cancel_saves_nothing(tmp_path):
    assert _process(tmp_path, [(0, 5, "en", ["Hello."])], cancel=True) is None
    assert not any(tmp_path.iterdir())


def test_reprocess_backs_up(tmp_path):
    _process(tmp_path, [(0, 5, "en", ["Hello."])])
    _process(tmp_path, [(0, 5, "en", ["Hello again."])], class_id="2026-11-18")
    folder = tmp_path / "2026-11-18"
    assert len(list(folder.glob("segments.*.json"))) == 1
    assert not (tmp_path / "2026-11-18-2").exists()
