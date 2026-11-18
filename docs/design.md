# Class Notes — Urdu/English class recordings → English translation notes

Design doc · 2026-11-18

## Intent

Quran classes are taught mostly in Urdu, and the teacher sometimes switches to English
for questions and explanations. The goal is a local Windows desktop app that turns each
recording into **English translation notes whose meaning can be trusted**:

- the teacher's English is kept exactly as spoken (not "translated" or paraphrased),
- Urdu is translated literally, sentence by sentence, with **no LLM**,
- the original Urdu stays next to every English line, so anyone fluent can check it,
- every line is timestamped and clickable, so you can hear exactly what was said.

The output is also the foundation for a later "second brain" (RAG over all classes), so
the saved data must be structured, timestamped and lossless.

## Goals

1. Open a class recording (mp3/m4a/wav/…), process it fully offline on the RTX 5060.
2. Show the result as a list of segments: time · language · Urdu source · English.
3. Click a segment → audio plays from that moment.
4. Save each class as `segments.json` (source of truth) plus readable `notes.md` and `.srt`.
5. Let a fluent reader correct an English line; the correction is stored *alongside* the
   machine output, never replacing it.
6. Keep a library of processed classes in the app's sidebar.

## Non-goals (v1)

- Live microphone / real-time captions.
- Any LLM step (cleanup, summaries, tagging).
- Speaker diarization (teacher vs students).
- The second brain itself — v1 only produces data in a RAG-ready shape.
- Quran ayah detection / inserting canonical verse text.
- An installer or sharing with other PCs (it runs from the project folder for now).

## Anti-goals (failure even if it "works")

- English that silently changes meaning with no way to check it → Urdu source is always kept and shown.
- Machine output lost or overwritten by edits or re-runs.
- Audio or text leaving the machine.
- Quranic recitation run through Urdu→English translation and shown as if it were meaning.

## Constraints

- Windows 11, i5-14600K, 16 GB RAM, **RTX 5060 8 GB (Blackwell, sm_120)**.
- Blackwell needs CUDA 12.8-era builds. CTranslate2's support for this card must be proven by
  a smoke test **before** anything else is built. Fallback: CPU int8 (slow but correct).
- System Python is 3.14 (too new for parts of the ML stack) → project pins **Python 3.12 via `uv`**.
- No ffmpeg installed; faster-whisper decodes audio via PyAV, so none is needed.
- VRAM budget: Whisper large-v3 fp16 (~3.5–4.5 GB) + NLLB-600M int8 (~1 GB) fit together.

## Approaches considered

| | Approach | Trade-off |
|---|---|---|
| **Chosen** | **Python core (faster-whisper + CTranslate2 NLLB) in a PySide6/Qt desktop window** | Fastest to build and change; same inference speed (the heavy work is compiled CUDA either way). Sharing later needs a large (~2–3 GB) bundle. |
| | Full C++ (whisper.cpp + CTranslate2 C++ + Qt) | Small single .exe, no Python. Requires CUDA Toolkit + building CTranslate2 from source on Windows for sm_120; weeks instead of days; no real speed gain. |
| | Python backend + web UI | Discussed earlier; you chose a native PC app instead. |

You picked the Python core in a desktop window. The pipeline is a few hundred lines, so a
C++ port later stays realistic; models and JSON format would carry over unchanged.

## Pipeline (as decided in the shared conversation)

```
audio ─► decode 16 kHz mono
      ─► Silero VAD (faster_whisper.vad.get_speech_timestamps)
      ─► language ID per span (Whisper detect_language, restricted set)
      ─► merge adjacent same-language spans (gap < 1 s, cap ~25 s)
      ─► per merged span:
            en → Whisper transcribe (language="en")            text = as spoken
            ur → Whisper transcribe (language="ur")            source = Urdu
                 → split into sentences → NLLB urd_Arab→eng_Latn  text = translation
            ar → Whisper transcribe (language="ar")            marked recitation, NOT translated
      ─► segments.json, notes.md, .srt
```

Details:

- **VAD:** `min_silence_duration_ms=500`, `max_speech_duration_s=20` (configurable).
- **Language ID:** probabilities summed into three buckets: Urdu = `ur`+`hi` (Urdu is often
  detected as Hindi), English = `en`, Arabic = `ar`. Spans < 1.5 s or with winning-bucket
  share < 0.7 default to Urdu (as in the conversation).
- **Arabic / recitation bucket — my call.** Adding `ar` to the language set costs almost
  nothing and stops recitation being fed into the Urdu translator. Such segments are shown
  as "Recitation (Arabic)" with Whisper's Arabic text and no English. Inserting canonical
  ayah text stays out of scope.
- **Whisper:** `large-v3` (not turbo — turbo can't translate and is weaker on Urdu),
  fp16 on CUDA, `beam_size=5`, `condition_on_previous_text=False` (reduces runaway
  repetition on long files).
- **Vocabulary prompt:** a user-editable glossary (surah names, tajweed, tafseer, the
  teacher's common phrases) passed as `initial_prompt` / `hotwords`.
- **Translator: NLLB-200 distilled 600M**, converted once to CTranslate2 int8 format.
  Translated per sentence (split on `۔ ؟ ! ?` and Whisper segment boundaries), so the
  model can't summarise or drop text across sentences. **My call over IndicTrans2:** NLLB
  is a single model with a standard tokenizer and is much simpler to run; IndicTrans2 is
  often a bit better on Urdu but needs its own preprocessing toolkit. The translator sits
  behind a small interface so IndicTrans2 can be swapped in after comparing on real
  recordings. (NLLB's licence is non-commercial — fine for class notes.)
- **Mid-sentence code-switching** ("Toh is ayat mein, what do you think it means?") stays
  one span and is treated as Urdu. Known limitation, accepted in the conversation.

## Data format (source of truth)

One folder per class: `library/<class_id>/`

`segments.json`
```json
{
  "schema_version": 1,
  "class_id": "2026-11-18",
  "title": "Surah Al-Kahf, ayat 1–10",
  "date": "2026-11-18",
  "audio_path": "D:/Quran class/2026-11-18.m4a",
  "duration_s": 3612.4,
  "models": {"asr": "whisper-large-v3", "mt": "nllb-200-distilled-600M-ct2-int8"},
  "created_at": "2026-11-18T19:04:11",
  "segments": [
    {"id": 17, "start": 812.4, "end": 829.1, "lang": "ur", "lang_conf": 0.93,
     "source": "…Urdu as transcribed…",
     "text": "…machine English…",
     "text_edited": null,
     "surah": null, "topic": null}
  ]
}
```

- `source` = what was said, in its own script (Urdu, English or Arabic).
- `text` = machine English (equals `source` for English; empty for recitation).
- `text_edited` = a human correction, or null. Notes/exports prefer it when present.
- Recordings are **referenced by path, not copied** (they're large). If the file has moved,
  the app asks you to locate it.
- Re-processing a class writes a new `segments.json` and keeps the previous one as
  `segments.<timestamp>.json`, so nothing is lost.

`notes.md` — date/title header, then one block per segment: `[13:32] (Urdu) English…` with
the Urdu underneath. `.srt` — English subtitles for any media player.

## The app (PySide6)

```
┌ Class Notes ─────────────────────────────────────────────────────────────┐
│ [+ New class]            │ Surah Al-Kahf, ayat 1–10 · 2026-11-18          │
│ ─────────────            │ ▶ ━━━━━━━●━━━━━━━━━━━━━  13:32 / 1:00:12      │
│ 2026-11-18 Al-Kahf 1–10  │ ─────────────────────────────────────────────  │
│ 2026-11-11 Al-Kahf intro │ 13:32  UR  اس آیت میں اللہ تعالیٰ فرماتے ہیں…   │
│ 2026-11-04 Tajweed rules │            In this verse Allah says…   ✎       │
│                          │ 13:49  EN  What do you think it means?         │
│                          │ 14:02  AR  ﴿ الْحَمْدُ لِلَّهِ الَّذِي … ﴾  recitation │
│                          │ …                                              │
│ ⚙ Glossary · Settings    │ [Export notes.md] [Export .srt] [Re-process]   │
└──────────────────────────┴───────────────────────────────────────────────┘
```

- **New class:** pick a file, date (defaults to file date), optional title → processing
  runs in a background worker with a progress bar (stage + % of audio done) and Cancel.
  Segments appear in the list as they finish. The window never freezes.
- **Segment list:** time, language badge, source (Urdu right-to-left in an Urdu-capable
  font), English below. Click → seek and play. The row being played is highlighted.
- **Edit:** ✎ on a row opens the English for correction → saved to `text_edited`;
  the row shows it was edited and can be reverted to the machine text.
- **Settings:** glossary, VAD/threshold values, device (GPU / CPU fallback), library folder.
- **First run:** if models are missing, a setup step downloads Whisper large-v3 and the
  NLLB weights and converts NLLB to CTranslate2 (one-time, several GB, shows progress).

## Project layout (builder's guide, not binding)

```
class-notes/
  pyproject.toml              # uv, Python 3.12
  src/classnotes/
    audio.py                  # decode, slicing
    segment.py                # VAD, language ID, merge  (pure logic, unit-tested)
    asr.py                    # Whisper wrapper
    translate.py              # Translator interface + NLLB impl, sentence split
    pipeline.py               # orchestrates, emits progress, cancellable
    store.py                  # segments.json read/write/backup, notes.md, srt
    models.py                 # download + NLLB conversion
    ui/                       # PySide6 main window, worker thread, dialogs
  tests/
  scripts/smoke_gpu.py        # proves CTranslate2 + CUDA on the RTX 5060
```

## Verification

1. `smoke_gpu.py` loads Whisper large-v3 and NLLB on CUDA and runs both. Must pass first.
2. Unit tests for the merge/threshold logic, sentence splitting, JSON round-trip, backups,
   notes/srt export (synthetic data, no models).
3. End-to-end on a short generated English clip (Windows text-to-speech) to prove the app
   flow without needing Urdu audio.
4. **A real class recording** (10 minutes with plenty of switching) is the real test:
   are English parts verbatim, do Urdu translations read faithfully, is recitation flagged.

## Left to the builder

Exact widget structure, threading mechanism (QThread vs subprocess, as long as the UI stays
responsive and Cancel works), styling, the Urdu font choice (Windows ships "Urdu
Typesetting"; Noto Nastaliq Urdu can be bundled), how progress is reported, and test layout.
