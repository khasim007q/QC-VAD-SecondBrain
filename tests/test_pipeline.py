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
        self.batches = []
        self.redone = []

    def speech_spans(self, audio):
        return [(int(a * SR), int(b * SR)) for a, b, _, _ in self.spans]

    def _texts(self, clip):
        idx = sorted({int(v) for v in np.unique(clip) if v >= 0})
        return [t for i in idx for t in self.spans[i][3]]

    def transcribe_batch(self, clips, prompts, choose):
        # language comes from the block's first scripted span, like detection on its start
        self.batches.append(len(clips))
        out = []
        for clip in clips:
            lang, conf = choose(PROBS[self.spans[int(clip[0])][2]], len(clip))
            self.prompts.append((lang, prompts[lang]))
            out.append((lang, conf, self._texts(clip), -0.25))
        return out

    def transcribe(self, clip, lang, prompt):
        self.redone.append(lang)
        self.prompts.append((lang, prompt))
        return self._texts(clip)


class FakeTranslator:
    def __init__(self):
        self.seen = []
        self.calls = 0

    def translate_scored(self, sentences):
        self.calls += 1
        self.seen.extend(sentences)
        return [("EN:" + s, -0.5) for s in sentences]

    def translate(self, sentences):
        return [t for t, _ in self.translate_scored(sentences)]


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
    result, got, *_ = run(spans, cancel_after=1, settings=Settings(batch_size=1))
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
    assert rec.models["asr"] == "whisper-large-v3-turbo"
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


def test_pipeline_applies_terms_before_translation_but_keeps_source():
    spans = [(0, 5, "ur", ["حضرت عمر آئے۔"])]
    result, _, _, _, tr = run(spans, settings=Settings(terms="حضرت = Hazrat"))
    assert tr.seen == ["Hazrat عمر آئے۔"]
    assert result[0].source == "حضرت عمر آئے۔"


def test_pipeline_batches_blocks_and_translates_once_per_batch():
    spans = [(0, 5, "ur", ["ایک۔"]), (10, 15, "ur", ["دو۔"]), (20, 25, "ur", ["تین۔"])]
    result, _, _, asr, tr = run(spans, settings=Settings(batch_size=2))
    assert asr.batches == [2, 1]
    assert tr.calls == 2
    assert [s.text for s in result] == ["EN:ایک۔", "EN:دو۔", "EN:تین۔"]


def test_pipeline_merges_close_spans_before_choosing_language():
    spans = [(0, 5, "ur", ["پہلا۔"]), (5.5, 9, "en", ["Then English."])]
    result, *_ = run(spans)
    assert len(result) == 1 and result[0].lang == "ur"
    assert (result[0].start, result[0].end) == (0.0, 9.0)


def test_english_block_written_in_urdu_script_is_redone_as_urdu():
    spans = [(0, 5, "en", ["یہ دراصل اردو میں بولا گیا جملہ ہے۔"])]
    result, _, _, asr, tr = run(spans)
    assert asr.redone == ["ur"]
    assert result[0].lang == "ur"
    assert tr.seen == ["یہ دراصل اردو میں بولا گیا جملہ ہے۔"]


def test_english_with_a_few_urdu_words_stays_english():
    spans = [(0, 5, "en", ["So this is called ہجرت in Urdu."])]
    result, _, _, asr, _ = run(spans)
    assert asr.redone == [] and result[0].lang == "en"


def test_overlong_speech_is_cut_into_whisper_sized_blocks():
    spans = [(0, 70, "en", ["Long talk."])]
    result, *_ = run(spans, settings=Settings(max_speech_s=90, merge_max_s=90))
    assert len(result) == 3
    assert all(s.end - s.start <= 30 for s in result)
    assert (result[0].start, result[-1].end) == (0.0, 70.0)


def test_pipeline_fixes_zuhr_in_prayer_context_before_translation():
    spans = [(0, 5, "ur", ["جمعہ آپ اکیلے پڑھیں گے تو زہر میں کاؤنٹ ہو جائے گا۔"])]
    result, _, _, _, tr = run(spans)
    assert tr.seen == ["جمعہ آپ اکیلے پڑھیں گے تو Zuhr میں کاؤنٹ ہو جائے گا۔"]
    assert "زہر" in result[0].source  # stored Urdu stays as heard


def test_segments_carry_whisper_and_nllb_scores():
    result, *_ = run([(0, 5, "ur", ["ایک۔", "دو۔"]), (10, 14, "en", ["Hello."])])
    ur, en = result
    assert ur.asr_logprob == -0.25 and ur.mt_score == -0.5
    assert en.asr_logprob == -0.25 and en.mt_score is None


def test_redone_english_block_has_no_whisper_score():
    result, *_ = run([(0, 5, "en", ["یہ دراصل اردو میں بولا گیا جملہ ہے۔"])])
    assert result[0].asr_logprob is None
