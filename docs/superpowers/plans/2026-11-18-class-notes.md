# Class Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local Windows desktop app that turns Urdu/English Quran-class recordings into timestamped English translation notes with the Urdu source kept beside every line.

**Architecture:** Pure-logic modules (segmentation, sentence split, storage/export) are unit-tested without models. Model wrappers (Whisper via faster-whisper, NLLB via CTranslate2) sit behind small protocols so the pipeline is tested with fakes. A PySide6 window runs the pipeline in a QThread and renders segments as they arrive.

**Tech Stack:** Python 3.12 (uv), faster-whisper (CTranslate2, CUDA 12), NLLB-200-distilled-600M converted to CTranslate2 int8, transformers tokenizer (runtime) + torch CPU (one-time conversion only), PySide6 (QtMultimedia for playback), platformdirs, pytest.

**Spec:** `docs/design.md`

## Global Constraints

- Python pinned to 3.12 via `uv` (`requires-python = ">=3.12,<3.13"`).
- Whisper model: `large-v3` (never turbo), fp16 on CUDA, `beam_size=5`, `condition_on_previous_text=False`.
- NLLB: `facebook/nllb-200-distilled-600M`, src `urd_Arab`, tgt `eng_Latn`, CTranslate2 `int8_float16` on CUDA (`int8` on CPU).
- VAD defaults: `min_silence_duration_ms=500`, `max_speech_duration_s=20`.
- Language buckets: ur = ur+hi, en = en, ar = ar. Span < 1.5 s or winning share < 0.7 → `ur`.
- Merge adjacent same-language spans when gap < 1.0 s and merged length ≤ 25 s.
- `ar` segments: transcribed in Arabic, `text = ""`, never translated.
- Nothing leaves the machine; no LLM anywhere.
- Machine output is never overwritten: edits go to `text_edited`; re-processing backs up the previous `segments.json`.
- Recordings are referenced by path, not copied.
- App data (models, settings): `platformdirs.user_data_dir("ClassNotes")`. Library default: `~/Documents/ClassNotes`.

## Review Focus

1. Recording with no speech (silence, music) → zero spans → a saved record with no segments; the UI says "No speech found" instead of crashing. (Task 4 test `test_pipeline_no_speech`.)
2. Whisper returns empty/whitespace text for a span → no blank rows in the notes. (Task 4 test `test_pipeline_skips_empty_text`.)
3. Cancel mid-run, or a crash while saving → previous `segments.json` intact, never a half-written file. (Task 3 `test_save_is_atomic_and_backs_up`, Task 4 `test_pipeline_cancel`.)
4. Long Urdu passage with no `۔`/`؟` punctuation → still split into translator-sized pieces (≤ 300 chars) so NLLB doesn't truncate. (Task 3 `test_split_long_unpunctuated`.)
5. Two classes on the same date, and a recording later moved/deleted → unique ids (`2026-11-18`, `2026-11-18-2`); record still loads and the UI offers to locate the file. (Task 3 `test_new_class_id_unique`, `test_load_with_missing_audio`.)

---

### Task 1: Scaffold, model setup, GPU smoke test

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `README.md`, `src/classnotes/__init__.py`, `src/classnotes/paths.py`, `src/classnotes/models.py`, `scripts/smoke_gpu.py`

**Interfaces:**
- Produces: `paths.data_dir() -> Path`, `paths.models_dir() -> Path`, `paths.default_library_dir() -> Path`; `models.whisper_dir() -> Path`, `models.nllb_dir() -> Path`, `models.ensure_whisper(progress: Callable[[str], None] | None = None) -> Path`, `models.ensure_nllb(progress=None) -> Path` (downloads + converts with `ctranslate2.converters.TransformersConverter`, quantization `int8_float16`, copies tokenizer files into the output dir), `models.models_ready() -> bool`, `models.cuda_available() -> bool` (`ctranslate2.get_cuda_device_count() > 0`).
- Dependencies: runtime `faster-whisper>=1.1`, `ctranslate2>=4.5`, `transformers`, `sentencepiece`, `numpy`, `PySide6`, `platformdirs`, `nvidia-cublas-cu12`, `nvidia-cudnn-cu12>=9`; group `convert`: `torch` (CPU index); group `dev`: `pytest`.
- On Windows, the nvidia pip packages' `bin` dirs must be added with `os.add_dll_directory` before importing ctranslate2 — do this in `classnotes/__init__.py`.

- [ ] Step 1: `uv sync` with all groups. Expected: env created on 3.12.
- [ ] Step 2: Write `scripts/smoke_gpu.py`: print cuda device count, ensure both models, load Whisper large-v3 on cuda fp16, transcribe 3 s of silence + a synthesized tone without error, translate `["یہ ایک کتاب ہے۔"]` with NLLB and print the English.
- [ ] Step 3: Run `uv run python scripts/smoke_gpu.py`. Expected: device count ≥ 1, an English sentence like "This is a book." If CUDA fails on the RTX 5060, record the error and switch defaults to CPU (`int8`) before continuing.
- [ ] Step 4: Commit `feat: project scaffold, model setup, GPU smoke test`.

### Task 2: Segmentation logic (`segment.py`)

**Files:** Create `src/classnotes/segment.py`, `tests/test_segment.py`

**Interfaces:**
- Produces:
  - `@dataclass LangSpan(start: int, end: int, lang: str, conf: float)` (sample offsets at 16 kHz)
  - `bucket_probs(probs: Iterable[tuple[str, float]]) -> dict[str, float]` → keys exactly `ur`, `en`, `ar`
  - `choose_lang(buckets: dict[str,float], n_samples: int, sr=16000, min_conf=0.7, min_dur_s=1.5) -> tuple[str, float]` — conf = winner / (ur+en+ar+1e-9)
  - `merge_spans(spans: list[LangSpan], sr=16000, max_gap_s=1.0, max_len_s=25.0) -> list[LangSpan]` — merged conf = min of parts

- [ ] Step 1: Tests:
  - `test_bucket_sums_hindi_into_urdu`: `[("ur",.3),("hi",.4),("en",.2),("ar",.05),("fr",.05)]` → `{"ur":.7,"en":.2,"ar":.05}` (approx)
  - `test_choose_english_when_confident`: `{"ur":.1,"en":.9,"ar":0}`, 3 s → `("en", ~0.9)`
  - `test_choose_arabic`: `{"ur":.1,"en":.05,"ar":.85}`, 5 s → `"ar"`
  - `test_short_span_defaults_to_urdu`: en .95 but 1.0 s → `"ur"`
  - `test_low_confidence_defaults_to_urdu`: `{"ur":.4,"en":.6,"ar":0}` → `"ur"`
  - `test_merge_same_lang_small_gap`: two `ur` spans gap 0.5 s → one span
  - `test_no_merge_across_language` / `test_no_merge_big_gap` (1.5 s) / `test_no_merge_over_max_len` (two 15 s spans)
- [ ] Step 2: Run `uv run pytest tests/test_segment.py` → FAIL. Step 3: implement. Step 4: PASS. Step 5: commit `feat: language bucketing and span merging`.

### Task 3: Sentence split, translator, storage/export

**Files:** Create `src/classnotes/translate.py`, `src/classnotes/store.py`, `tests/test_translate.py`, `tests/test_store.py`

**Interfaces:**
- `translate.split_sentences(texts: list[str], max_chars=300) -> list[str]` — split on `۔ ؟ ! ? .` keeping the mark; pieces over `max_chars` split at `،`/`,` then whitespace; drop empty.
- `translate.Translator` protocol: `translate(sentences: list[str]) -> list[str]` (same length, same order).
- `translate.NllbTranslator(model_dir: Path, device: str)` — batch size 16, `beam_size=4`, `target_prefix=[["eng_Latn"]]`, `max_decoding_length=256`.
- `store.Segment` dataclass: `id:int, start:float, end:float, lang:str, lang_conf:float, source:str, text:str, text_edited:str|None=None, surah:str|None=None, topic:str|None=None`.
- `store.ClassRecord` dataclass: `class_id, title, date, audio_path, duration_s, models: dict, created_at, segments: list[Segment], schema_version: int = 1`.
- `store.display_text(seg) -> str` (edited if set, else text).
- `store.new_class_id(library: Path, date: str) -> str`.
- `store.class_dir(library, class_id) -> Path`.
- `store.save_record(rec, library) -> Path` — writes to `segments.json.tmp` then `os.replace`; if `segments.json` existed and this is a re-process (`backup=True`), first copies it to `segments.<YYYYmmdd-HHMMSS>.json`. Also writes `notes.md` and `<class_id>.srt`.
- `store.load_record(folder: Path) -> ClassRecord`; `store.list_library(library) -> list[ClassRecord]` (newest date first, unreadable folders skipped).
- `store.render_notes_md(rec) -> str` — header `# {title}` + `{date}` line; per segment `**[MM:SS]** *(Urdu|English|Recitation)* {display_text}` and, for non-English, the source on the next line as a blockquote; times ≥ 1 h as `H:MM:SS`.
- `store.render_srt(rec) -> str` — skips `ar` and empty-text segments; numbering contiguous; `HH:MM:SS,mmm`.

- [ ] Step 1: Tests:
  - `test_split_on_urdu_marks`: `["پہلا جملہ۔ دوسرا؟ third one."]` → 3 pieces
  - `test_split_long_unpunctuated`: 1000-char unpunctuated string → all pieces ≤ 300, joined words == original words
  - `test_split_drops_empty`: `["  ", "۔"]` → `[]`
  - `test_roundtrip`, `test_display_text_prefers_edit`
  - `test_save_is_atomic_and_backs_up`: save, save again with backup=True → one backup file, no `.tmp` left, latest content loaded
  - `test_new_class_id_unique`: existing `2026-11-18` → `2026-11-18-2`
  - `test_load_with_missing_audio`: audio_path points nowhere → loads fine
  - `test_list_library_skips_corrupt`
  - `test_notes_md_contains_source_and_edit`, `test_srt_skips_recitation_and_formats_time` (3725.5 s → `01:02:05,500`)
- [ ] Step 2: FAIL. Step 3: implement. Step 4: PASS. Step 5: commit `feat: sentence splitting, NLLB translator, class storage and export`.

### Task 4: Whisper wrapper and pipeline

**Files:** Create `src/classnotes/settings.py`, `src/classnotes/asr.py`, `src/classnotes/pipeline.py`, `tests/test_pipeline.py`

**Interfaces:**
- `settings.Settings` dataclass: `glossary: str = <default Islamic terms>`, `min_silence_ms=500`, `max_speech_s=20.0`, `min_conf=0.7`, `min_dur_s=1.5`, `merge_gap_s=1.0`, `merge_max_s=25.0`, `device="auto"`, `library_dir: str`; `Settings.load() -> Settings`, `.save()`, `.resolved_device() -> "cuda"|"cpu"`.
- `asr.Asr` protocol: `speech_spans(audio) -> list[tuple[int,int]]`, `lang_probs(clip) -> list[tuple[str,float]]`, `transcribe(clip, lang: str, prompt: str|None) -> list[str]`.
- `asr.WhisperAsr(model_dir, device, settings)` — `get_speech_timestamps(audio, VadOptions(...))`; `model.detect_language(clip)` third return value; `model.transcribe(clip, language=lang, task="transcribe", beam_size=5, condition_on_previous_text=False, initial_prompt=prompt, vad_filter=False)`.
- `audio.load_audio(path) -> np.ndarray` (faster_whisper.decode_audio at 16 kHz; raise `AudioError(str)` on failure) — put in `asr.py`.
- `pipeline.run_pipeline(audio, asr, translator, settings, on_segment: Callable[[Segment],None], on_progress: Callable[[str, float],None], cancelled: Callable[[],bool]) -> list[Segment] | None` — returns None if cancelled. Progress stages: `"Finding speech"`, `"Detecting language"`, `"Transcribing"` with fraction = processed samples / total speech samples. Prompt for `ur`/`en` = glossary; none for `ar`.
- Segment ids are contiguous from 0 in time order; segments with empty source are dropped.

- [ ] Step 1: Tests with `FakeAsr` (spans and per-span lang/texts scripted) and `FakeTranslator` (prefixes `EN:`):
  - `test_pipeline_routes_by_language`: en span → `text == source`; ur span → `text == "EN:…"`; ar span → `text == ""`, translator never received Arabic
  - `test_pipeline_no_speech` → `[]`, progress reached 1.0
  - `test_pipeline_skips_empty_text`
  - `test_pipeline_cancel`: `cancelled` true after first segment → returns None
  - `test_pipeline_merges_neighbours`: two close ur spans → one segment
- [ ] Step 2: FAIL. Step 3: implement. Step 4: PASS. Step 5: commit `feat: Whisper wrapper and processing pipeline`.

### Task 5: Desktop UI

**Files:** Create `src/classnotes/ui/__init__.py`, `ui/app.py` (entry `main()`), `ui/main_window.py`, `ui/worker.py`, `ui/dialogs.py`, `ui/segment_view.py`; `pyproject.toml` script `classnotes = "classnotes.ui.app:main"`; `run.bat`.

**Interfaces:** consumes everything above.

Behaviour (from spec "The app"):
- Sidebar: library list (date · title), `+ New class`, `Glossary & Settings`.
- New class dialog: file picker (audio filter), date (default file mtime), title → creates `ProcessWorker(QThread)` with signals `segment(Segment)`, `progress(str, float)`, `finished(ClassRecord)`, `failed(str)`; Cancel button sets a flag. First run: if `models_ready()` is false, a setup dialog runs `ensure_whisper/ensure_nllb` in a thread with log output.
- Segment view: `QListView` + custom delegate or `QTableWidget` — time, language badge, source (Urdu RTL, font "Urdu Typesetting" fallback "Segoe UI"), English below; click → `QMediaPlayer.setPosition` + play; current row highlighted from `positionChanged`.
- Edit (double-click / ✎): `QInputDialog.getMultiLineText` prefilled with display text → sets `text_edited` (empty → revert to None) → `save_record(backup=False)`.
- Player bar: play/pause, slider, time label. Missing audio → banner with "Locate recording…" that updates `audio_path` and saves.
- Buttons: Export notes.md / .srt (QFileDialog save), Re-process (backup=True).
- "No speech found" label when a record has zero segments.
- Errors (AudioError, model failures) → QMessageBox, app stays alive.

- [ ] Step 1: Implement. Step 2: `uv run python -c "import classnotes.ui.main_window"` imports clean. Step 3: Launch with `QT_QPA_PLATFORM=offscreen` and a test that constructs `MainWindow` with a temp library containing one fixture record (`tests/test_ui_smoke.py`, uses `pytest-qt`-free plain QApplication) → window builds, list has 1 row, segment view shows N rows. Step 4: Commit `feat: desktop UI`.

### Task 6: End-to-end check and publish

- [ ] Step 1: Generate a ~20 s English clip with Windows SAPI (`System.Speech`) to `tests/data/en_clip.wav` (gitignored), run the pipeline headless via `scripts/process_file.py <audio> --library <tmp>` (create it: CLI using the same modules), confirm segments.json has `en` segments matching the spoken text.
- [ ] Step 2: Launch the app, process the same clip through the UI, click a row, confirm playback seeks.
- [ ] Step 3: README with setup (`uv sync`, `uv run python -m classnotes.models` to fetch models, `run.bat`) and usage.
- [ ] Step 4: Commit, `git remote add origin https://github.com/khasim007q/QC-VAD-SecondBrain.git`, `git push -u origin main`.
- [ ] Step 5: Real 10-minute class recording from the user → review English verbatim, Urdu faithful, recitation flagged.
