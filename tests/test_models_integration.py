"""Runs real models when they are downloaded; skipped otherwise."""
import pytest

from classnotes import models

pytestmark = pytest.mark.skipif(not models.models_ready(), reason="models not downloaded")


def test_nllb_translates_urdu_sentences():
    from classnotes.translate import NllbTranslator

    tr = NllbTranslator(models.nllb_dir(), "cuda" if models.cuda_available() else "cpu")
    out = tr.translate(["یہ ایک کتاب ہے۔", "آج موسم بہت اچھا ہے۔"])
    assert len(out) == 2
    assert "book" in out[0].lower()
    assert "weather" in out[1].lower() or "today" in out[1].lower()
    assert all("eng_Latn" not in s and "</s>" not in s for s in out)


def test_nllb_does_not_loop():
    from classnotes.translate import NllbTranslator

    looping = ("تیک اویز، تیک اویز میں کریں گے کیا، ہجرت تو کر نہیں سکتے، کریں گے کیا تیک اویز میں، "
               "ہجرت کے جو سبق ہے اس کو اپنی زندگی میں implement کرنے کی کوشش کریں گے")
    tr = NllbTranslator(models.nllb_dir(), "cuda" if models.cuda_available() else "cpu")
    words = tr.translate([looping])[0].split()
    grams = [tuple(words[i:i + 4]) for i in range(len(words) - 3)]
    assert len(words) < 60
    assert len(grams) == len(set(grams))


def test_whisper_batch_runs_language_and_text_in_one_pass():
    import numpy as np

    from classnotes.asr import WhisperAsr
    from classnotes.segment import bucket_probs, choose_lang
    from classnotes.settings import Settings

    device = "cuda" if models.cuda_available() else "cpu"
    asr = WhisperAsr(models.whisper_dir(), device, Settings())
    rng = np.random.default_rng(0)
    clips = [rng.normal(0, 0.01, 16000 * n).astype(np.float32) for n in (3, 8)]
    seen = []

    def choose(probs, n):
        seen.append(n)
        return choose_lang(bucket_probs(probs), n)

    out = asr.transcribe_batch(clips, {"ur": "قرآن", "en": "Quran", "ar": None}, choose)
    assert len(out) == 2 and seen == [16000 * 3, 16000 * 8]
    assert all(len(r) == 4 for r in out)
    assert all(lang in ("ur", "en", "ar") and isinstance(texts, list) and (lp is None or isinstance(lp, float))
               for lang, _, texts, lp in out)


def test_nllb_scores_its_translations():
    from classnotes.translate import NllbTranslator

    tr = NllbTranslator(models.nllb_dir(), "cuda" if models.cuda_available() else "cpu")
    out = tr.translate_scored(["یہ ایک کتاب ہے۔"])
    assert len(out) == 1 and "book" in out[0][0].lower() and out[0][1] < 0
