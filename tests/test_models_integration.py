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
