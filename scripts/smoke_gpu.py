"""Prove Whisper large-v3 and NLLB run on this machine's GPU (falls back to CPU report)."""

import sys
import time

import numpy as np

import classnotes  # noqa: F401  (registers CUDA DLL dirs)
import ctranslate2
from classnotes import models

device = sys.argv[1] if len(sys.argv) > 1 else ("cuda" if models.cuda_available() else "cpu")
print("ctranslate2", ctranslate2.__version__, "| CUDA devices:", ctranslate2.get_cuda_device_count())
if device == "cuda":
    print("CUDA compute types:", ctranslate2.get_supported_compute_types("cuda"))

models.ensure_whisper()
models.ensure_nllb()

from faster_whisper import WhisperModel  # noqa: E402

t = time.time()
w = WhisperModel(str(models.whisper_dir()), device=device,
                 compute_type="float16" if device == "cuda" else "int8")
print(f"Whisper loaded on {device} in {time.time() - t:.1f}s")
sr = 16000
tone = 0.1 * np.sin(2 * np.pi * 220 * np.arange(sr * 3) / sr).astype(np.float32)
audio = np.concatenate([np.zeros(sr * 3, np.float32), tone])
segs, info = w.transcribe(audio, language="ur", beam_size=5)
print("Whisper ran; segments:", [s.text for s in segs])
lang, prob, probs = w.detect_language(audio)
print("detect_language ok:", lang, round(prob, 3), "| top3:", probs[:3])

from classnotes.translate import NllbTranslator  # noqa: E402

tr = NllbTranslator(models.nllb_dir(), device)
print("NLLB:", tr.translate(["یہ ایک کتاب ہے۔", "اللہ تعالیٰ بہت مہربان ہے۔"]))
print("SMOKE OK on", device)
