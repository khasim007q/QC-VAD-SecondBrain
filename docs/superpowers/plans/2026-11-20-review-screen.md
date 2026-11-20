# Review Screen (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the rich-text window with a native Qt review screen built for listening straight
through and fixing lines: player with speed, stop-after-line and output picker, shortcuts, edit in
place, lines to check, search across classes, one Export menu, and light/dark themes that follow
Windows.

**Architecture:** Pure-Python logic in small modules (`flags.py`, `search.py`, `export.py`,
`ui/theme.py`, playback helpers in `ui/player.py`) tested without a window; thin Qt widgets
(`ui/line_view.py`, `ui/player.py`, `ui/sidebar.py`) assembled by `ui/main_window.py`. One widget
per line inside a `QScrollArea`; one QSS template filled from light or dark tokens.

**Tech Stack:** Python 3.12, PySide6 6.12 (QtWidgets, QtMultimedia), CTranslate2 / faster-whisper
(existing), python-docx (new), pytest.

**Spec:** `docs/superpowers/specs/2026-11-20-review-screen-design.md` (read it before any task).
Visual reference: `docs/design/drafts/a-reader.html` (light), `docs/design/drafts/b-inspector.html`
(dark colours, output picker), `docs/design/drafts/c-focus.html` (stop after this line).

## Global Constraints

- Native Qt widgets only. No `QWebEngineView` anywhere.
- Never change a segment's machine `text`; edits live in `text_edited`.
- Offline: fonts bundled as files in `src/classnotes/ui/fonts/` with their `OFL.txt`; nothing fetched at runtime.
- Schema 1 `segments.json` files must load unchanged (new fields take defaults).
- Light tokens: page `#f8f8f8`, surface `#eeeeee`, panel `#ffffff`, ink `#0a0a0a`, accent `#1f6b3a`, muted `#5b5f5c`, hairline ink 13%, flag dot `#b26b00`, flag label `#7a4b00`.
- Dark tokens: page `#161c1a`, surface `#1f2725`, panel `#26302d`, ink `#e3e2da`, accent `#9fc7b8`, accent label `#13201b`, muted `#a3a89f`, hairline ink 12%, flag dot `#e0a84f`, flag label `#e8bd73`.
- Contrast: body text 7:1 on its ground, labels and muted text 4.5:1, in both themes.
- Radius 8 / 12 / 20; spacing 4, 8, 12, 16, 24, 32, 48; read text 16px or more (English 17, Urdu 19 Nastaliq line-height 2.1); labels 13px weight 500; sentence case.
- One filled (accent) button per view; every other button is the outlined secondary; links are text links.
- Speeds exactly 0.75, 1.0, 1.25, 1.5, pitch kept (`QMediaPlayer.setPitchCompensation(True)`).
- Shortcuts never fire while focus is in a text field.
- Window minimum 1024x700. An 800-line class opens in under 1 second.
- Flags target 5 to 10% of a class's lines.
- Tests run with `QT_QPA_PLATFORM=offscreen`; command `uv run pytest`.

## Review Focus

1. **A class with no lines** ("No speech found"): the screen shows an empty state; Space, arrows, R, E, F do nothing and don't crash; every export writes a valid file. (Task 8 and Task 10 tests.)
2. **A very long line** (Session 19 has 600-character blocks): the edit box grows to fit, saves the whole text, and the Urdu label wraps right to left. (Task 8 test.)
3. **Search input that isn't a word:** one character, only vowel marks, or regex characters like `(`, `*`, `[`: no crash; under two letters shows the class list; `(` is matched literally. (Task 4 test.)
4. **Recording missing:** player controls disabled, shortcuts no-ops, the banner shows; editing still works. (Task 10 test.)
5. **Theme switches while editing:** the half-typed edit and the playing line survive the restyle. (Task 10 test.)

---

## File structure

| File | Responsibility |
|---|---|
| `src/classnotes/store.py` (modify) | `Segment` gains `asr_logprob`, `mt_score`, `checked`; schema 2 |
| `src/classnotes/settings.py` (modify) | `audio_output`, `playback_rate`, `stop_after_line`, `theme` |
| `src/classnotes/asr.py`, `translate.py`, `pipeline.py` (modify) | carry Whisper and NLLB scores into segments |
| `src/classnotes/flags.py` (new) | which lines to check, and why |
| `src/classnotes/search.py` (new) | search all classes |
| `src/classnotes/export.py` (new) | every export format |
| `src/classnotes/ui/theme.py` (new) | tokens, contrast check, QSS, fonts, theme resolution |
| `src/classnotes/ui/fonts/` (new) | bundled font files and licences |
| `src/classnotes/ui/player.py` (new) | playback controller (rates, stop-after-line, outputs) and the player bar |
| `src/classnotes/ui/line_view.py` (new) | the list of line widgets: highlight, follow, edit in place, flags |
| `src/classnotes/ui/sidebar.py` (new) | search field, class list, search results |
| `src/classnotes/ui/main_window.py` (rewrite) | assembles the screen, header, menus, shortcuts, processing |
| `src/classnotes/ui/dialogs.py` (modify) | Theme setting; `EditDialog` removed |
| `src/classnotes/ui/segment_view.py` (delete) | replaced by `line_view.py` |
| `src/classnotes/ui/app.py` (modify) | load fonts, apply theme, follow Windows |

---

### Task 1: Data model and settings

**Files:**
- Modify: `src/classnotes/store.py` (`Segment`, `ClassRecord.schema_version`)
- Modify: `src/classnotes/settings.py` (`Settings`)
- Test: `tests/test_store.py`, `tests/test_settings.py` (new)

**Interfaces:**
- Produces: `Segment(..., asr_logprob: float | None = None, mt_score: float | None = None, checked: bool = False)`; `ClassRecord.schema_version = 2`; `Settings.audio_output: str = ""`, `Settings.playback_rate: float = 1.0`, `Settings.stop_after_line: bool = False`, `Settings.theme: str = "system"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_store.py
def test_schema1_file_loads_with_new_defaults(tmp_path):
    folder = tmp_path / "c"; folder.mkdir()
    old = asdict(make_record()); old["schema_version"] = 1
    for s in old["segments"]:
        for k in ("asr_logprob", "mt_score", "checked"):
            s.pop(k, None)
    (folder / "segments.json").write_text(json.dumps(old, ensure_ascii=False), "utf-8")
    seg = store.load_record(folder).segments[0]
    assert (seg.asr_logprob, seg.mt_score, seg.checked) == (None, None, False)

def test_new_fields_roundtrip_and_schema_is_2(tmp_path):
    rec = make_record()
    rec.segments[0].asr_logprob, rec.segments[0].mt_score, rec.segments[0].checked = -0.42, -0.9, True
    loaded = store.load_record(store.save_record(rec, tmp_path))
    assert loaded == rec and loaded.schema_version == 2

# tests/test_settings.py
def test_new_settings_defaults():
    s = Settings()
    assert (s.audio_output, s.playback_rate, s.stop_after_line, s.theme) == ("", 1.0, False, "system")
```

- [ ] **Step 2: Run** `uv run pytest tests/test_store.py tests/test_settings.py -q` — expect FAIL (unknown fields / schema 1).
- [ ] **Step 3: Add the fields** with the defaults above; set `schema_version: int = 2`.
- [ ] **Step 4: Run** `uv run pytest -q` — expect all PASS.
- [ ] **Step 5: Commit** `git commit -am "feat: segment scores, checked flag and new settings (schema 2)"` (add `tests/test_settings.py`).

---

### Task 2: Store Whisper and NLLB scores in segments

**Files:**
- Modify: `src/classnotes/asr.py` (`BlockResult`, `WhisperAsr._batch`)
- Modify: `src/classnotes/translate.py` (`Translator`, `NllbTranslator`)
- Modify: `src/classnotes/pipeline.py` (`run_pipeline`, `_make_segments`, `_make_segment`)
- Test: `tests/test_pipeline.py`, `tests/test_models_integration.py`

**Interfaces:**
- Consumes: Task 1 `Segment.asr_logprob`, `Segment.mt_score`.
- Produces: `BlockResult = tuple[str, float, list[str], float | None]` (language, confidence, texts, average log-probability; `None` when the block was redone by `transcribe()`); `Translator.translate_scored(sentences: list[str]) -> list[tuple[str, float]]` (English, average token log-probability); `NllbTranslator.translate` stays and returns `[t for t, _ in translate_scored(...)]`.

- [ ] **Step 1: Write the failing tests** (update `FakeAsr.transcribe_batch` to return 4-tuples with logprob `-0.25`, and `FakeTranslator` to implement `translate_scored` returning `("EN:" + s, -0.5)`; `translate` delegates to it)

```python
def test_segments_carry_whisper_and_nllb_scores():
    result, *_ = run([(0, 5, "ur", ["ایک۔", "دو۔"]), (10, 14, "en", ["Hello."])])
    ur, en = result
    assert ur.asr_logprob == -0.25 and ur.mt_score == -0.5
    assert en.asr_logprob == -0.25 and en.mt_score is None

def test_redone_english_block_has_no_whisper_score():
    result, *_ = run([(0, 5, "en", ["یہ دراصل اردو میں بولا گیا جملہ ہے۔"])])
    assert result[0].asr_logprob is None
```

Integration (`tests/test_models_integration.py`): `NllbTranslator(...).translate_scored(["یہ ایک کتاب ہے۔"])` returns one pair whose float is `< 0`; the existing batch test asserts each result has 4 items and the 4th is a float or `None`.

- [ ] **Step 2: Run** `uv run pytest tests/test_pipeline.py -q` — expect FAIL.
- [ ] **Step 3: Implement.** `_batch` returns the `avg_logprob` it already computes (or `None` after the careful redo). `NllbTranslator.translate_scored` passes `return_scores=True` to `translate_batch`; the score is `r.scores[0]` (CTranslate2 already normalises by length). A segment's `mt_score` is the mean of its sentences' scores, rounded to 3 places; `asr_logprob` rounded to 3 places.
- [ ] **Step 4: Run** `uv run pytest -q` — expect all PASS (integration tests included when models exist).
- [ ] **Step 5: Commit** `git commit -am "feat: store Whisper and NLLB confidence per segment"`.

---

### Task 3: Lines to check

**Files:**
- Create: `src/classnotes/flags.py`
- Test: `tests/test_flags.py`

**Interfaces:**
- Consumes: `store.Segment` (Task 1).
- Produces: `flag_reason(seg: Segment) -> str | None`; `flagged_ids(segments: list[Segment]) -> list[int]`; `next_flagged(segments, after_id: int | None) -> int | None` (wraps round; `None` when nothing is flagged). Constants `MIN_LANG_CONF = 0.9`, `MAX_SHORT_WORDS = 2`, `MIN_WORD_RATIO`, `MIN_ASR_LOGPROB`, `MIN_MT_SCORE` (last three set in Step 4).

Reasons, checked in this order, exact text: `"Language unsure"`, `"Very short, may be noise"`, `"Translation may be missing words"`, `"Words may be misheard"`, `"Translation unsure"`. Never flagged: `text_edited` set, `checked` true, `lang == "ar"`. The word-ratio rule applies to Urdu segments only: English words / Urdu words below `MIN_WORD_RATIO`. Score rules skip `None`.

- [ ] **Step 1: Write the failing tests** — one per reason with a `Segment` built to trip exactly that rule; `test_edited_checked_and_recitation_are_never_flagged`; `test_next_flagged_wraps_round` (ids `[3, 7]`, after 7 → 3, after None → 3); `test_none_scores_are_ignored`.
- [ ] **Step 2: Run** `uv run pytest tests/test_flags.py -q` — expect FAIL (no module).
- [ ] **Step 3: Implement** `flag_reason`, `flagged_ids`, `next_flagged` with placeholder cut-offs `MIN_WORD_RATIO = 0.45`, `MIN_ASR_LOGPROB = -0.8`, `MIN_MT_SCORE = -1.2`.
- [ ] **Step 4: Calibrate on Session 19 without touching the user's class.** The user is editing `Documents/ClassNotes/2026-11-18` right now: never re-process or save it. Process the recording into a throwaway library in the scratchpad so the copy has scores: `uv run python -m classnotes.cli "C:/Users/HI/Downloads/19. YP05-Session 19-Hijrat e Rasool SAWS.mp3" --title "Session 19 calibration" --library <scratchpad>/calib`. Then print, for each rule alone, how many of its lines it flags, and set the three cut-offs so the total is 5 to 10% of its lines. Write the chosen numbers and the resulting count in a comment above the constants. The user's real class keeps working with the signals it has (no scores until it is re-processed).
- [ ] **Step 5: Run** `uv run pytest -q` — expect PASS. **Commit** `git commit -am "feat: flag lines to check, calibrated on Session 19"` (add `tests/test_flags.py`).

---

### Task 4: Search across classes

**Files:**
- Create: `src/classnotes/search.py`
- Test: `tests/test_search.py`

**Interfaces:**
- Consumes: `store.ClassRecord`, `store.display_text`.
- Produces: `normalize(text: str) -> str` (casefold, strip Arabic-script marks U+064B–U+065F, U+0670, U+06D6–U+06ED, collapse spaces); `@dataclass Hit(class_id: str, title: str, seg_id: int, start: float, snippet: str, match_start: int, match_end: int)` where `snippet` is ≤ 120 characters around the match and `match_start/end` index into `snippet`; `class SearchIndex: __init__(records: list[ClassRecord]); search(query: str, limit: int = 200) -> list[Hit]`. Matches English (edit and machine), Urdu `source`, and title (a title match returns one hit with `seg_id = -1`). Queries with fewer than 2 letters after normalising return `[]`. Plain substring matching (never regex).

- [ ] **Step 1: Write the failing tests**

```python
def test_finds_english_edit_and_urdu(tmp_path): ...       # "Sunnah" in text_edited, "سنتوں" in source -> 2 hits, right seg ids
def test_urdu_vowel_marks_are_ignored(): ...               # query "حضرت" finds source "حضرتِ ابوبکر"
def test_case_insensitive_english(): ...                    # "hijrat" finds "Hijrat"
def test_short_or_mark_only_queries_return_nothing(): ...   # "a", "ِ", "  " -> []
def test_regex_characters_are_literal(): ...                # "(SAW)" finds "Rasulullah (SAW)"; "*" and "[" -> [] without error
def test_snippet_bounds_the_match(): ...                    # snippet[match_start:match_end] normalises to the query; len <= 120
```

- [ ] **Step 2: Run** — expect FAIL. **Step 3: Implement.** Map normalised positions back to the original string when cutting the snippet (keep an index list while normalising). **Step 4: Run** `uv run pytest -q` — PASS.
- [ ] **Step 5: Commit** `git commit -m "feat: search across classes"` (add files).

---

### Task 5: Export formats

**Files:**
- Create: `src/classnotes/export.py`
- Modify: `pyproject.toml` (add `python-docx>=1.1`), `uv.lock` via `uv add python-docx`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `store.render_notes_md`, `store.render_srt`, `store.display_text`, `flags.flag_reason` (Task 3).
- Produces: `FORMATS: list[tuple[str, str, str]]` = `[("md","Notes",".md"), ("docx","Word document",".docx"), ("pdf","PDF",".pdf"), ("srt","Subtitles",".srt"), ("vtt","Web subtitles",".vtt"), ("txt","Plain text",".txt"), ("csv","Spreadsheet",".csv"), ("json","Data for search tools",".json")]`; `default_name(rec: ClassRecord, ext: str) -> str` = `f"{rec.class_id} {rec.title}{ext}"` with `\/:*?"<>|` removed; `export(rec: ClassRecord, kind: str, path: Path) -> None`.

Contents as the spec's Export table. Details the spec fixes: `.csv` columns `start,end,language,urdu,english_machine,english_edited,flag`, encoding `utf-8-sig`; `.vtt` starts `WEBVTT` then cues with `.` milliseconds; `.txt` lines `[mm:ss] English` (recitation lines `[mm:ss] (Recitation) <Arabic>`); `.json` is `asdict(rec)`. Word: title as heading, date line, then per line a time + English paragraph and an Urdu paragraph set right-to-left: on the paragraph `pPr` add `<w:bidi/>`, on each run `rPr` add `<w:rtl/>` and `<w:rFonts w:cs="Noto Nastaliq Urdu"/>`. PDF: build HTML (same order; Urdu in `<p dir="rtl">` with the Urdu family) into a `QTextDocument` and print with `QPdfWriter` (A4, 300 dpi); requires a `QGuiApplication`.

- [ ] **Step 1: Write the failing tests** — a parametrized `test_every_format_writes_a_readable_file(qapp, tmp_path, kind)` over `FORMATS` using `make_record()`: file exists and is non-empty; plus `md` equals `render_notes_md`, `docx` read back with `docx.Document` contains the edited English "The last" and Urdu "آخری" and an Urdu paragraph with `w:bidi`, `pdf` starts with `b"%PDF"`, `csv` starts with the BOM and has 4 data rows with header as above, `vtt` starts with `"WEBVTT"` and has `00:00:12.000 --> 00:00:20.500`, `json` loads back via `store.record_from_dict` equal to the record; `test_empty_class_exports_valid_files` (no segments, every kind writes; json/csv parse); `test_default_name_strips_forbidden_characters`.
- [ ] **Step 2: Run** — FAIL. **Step 3:** `uv add python-docx`, implement. **Step 4: Run** `uv run pytest -q` — PASS.
- [ ] **Step 5: Commit** `git commit -m "feat: export to md, docx, pdf, srt, vtt, txt, csv and json"` (add files, pyproject, lock).

---

### Task 6: Theme, fonts and contrast

**Files:**
- Create: `src/classnotes/ui/theme.py`
- Create: `src/classnotes/ui/fonts/` — download (ask the user first, naming each file and its size) from `https://github.com/google/fonts/raw/main/ofl/`: `familjengrotesk/FamiljenGrotesk[wght].ttf`, `familjengrotesk/OFL.txt`, `ibmplexmono/IBMPlexMono-Regular.ttf`, `ibmplexmono/IBMPlexMono-Medium.ttf`, `ibmplexmono/OFL.txt`, `notonastaliqurdu/NotoNastaliqUrdu[wght].ttf`, `notonastaliqurdu/OFL.txt`, `notonaskharabic/NotoNaskhArabic[wght].ttf`, `notonaskharabic/OFL.txt` (licences saved as `<Family>-OFL.txt`)
- Modify: `pyproject.toml` (include `ui/fonts/*` and `ui/*.png|ico` in the wheel)
- Modify: `src/classnotes/ui/app.py`
- Test: `tests/test_theme.py`

**Interfaces:**
- Produces: `LIGHT: dict[str, str]`, `DARK: dict[str, str]` with keys `page, surface, panel, ink, accent, accent_label, muted, line, line_strong, flag_dot, flag_label` (values from Global Constraints; `accent_label` light is `#ffffff`); `contrast(fg: str, bg: str) -> float` (WCAG relative luminance; rgba hairlines composited on `page`); `resolve(setting: str, scheme: Qt.ColorScheme) -> str` returning `"light"`/`"dark"` (`"system"` maps `Dark` → dark, anything else → light); `qss(tokens: dict[str, str]) -> str`; `load_fonts() -> dict[str, str]` returning family names for keys `ui, mono, urdu, arabic` (falls back to `"Segoe UI"`, `"Consolas"`, `"Urdu Typesetting"`, `"Arial"` when a file is missing); `apply(app: QApplication, settings: Settings) -> str` sets the stylesheet and returns the theme applied.
- `qss` uses object names that later tasks set: `#Sidebar`, `#Header`, `#LineList`, `#Line`, `#Line[playing="true"]`, `#Line[flagged="true"]`, `#PlayerBar`, `QPushButton[kind="primary"]`, `QPushButton[kind="secondary"]`, `QPushButton[kind="link"]`, `#Notice`, `#Banner`, `#Key` (small key labels).

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("t", [LIGHT, DARK])
def test_text_pairs_meet_contrast(t):
    assert contrast(t["ink"], t["page"]) >= 7 and contrast(t["ink"], t["panel"]) >= 7
    assert contrast(t["muted"], t["page"]) >= 4.5 and contrast(t["muted"], t["panel"]) >= 4.5
    assert contrast(t["flag_label"], t["panel"]) >= 4.5 and contrast(t["accent_label"], t["accent"]) >= 4.5
    assert contrast(t["accent"], t["page"]) >= 3

def test_resolve_follows_windows_only_for_system(): ...   # ("system", Dark)->"dark", ("system", Light)->"light", ("light", Dark)->"light", ("dark", Light)->"dark"
def test_qss_uses_the_tokens(): ...                        # every LIGHT value appears in qss(LIGHT); no "{" placeholders left
def test_fonts_load(qapp): ...                             # load_fonts()["urdu"] == "Noto Nastaliq Urdu" when the file exists
```

If a contrast pair fails, adjust only that token by the smallest step that passes and note the change in a comment.

- [ ] **Step 2: Run** — FAIL. **Step 3:** Download fonts (after the user's OK), implement `theme.py`; in `app.main()` call `load_fonts()`, `apply()`, and connect `app.styleHints().colorSchemeChanged` to re-apply when `settings.theme == "system"`. Remove `app.setStyle("Fusion")` only if QSS covers every widget; otherwise keep Fusion under the QSS.
- [ ] **Step 4: Run** `uv run pytest -q` — PASS. **Step 5: Commit** `git commit -m "feat: light and dark themes with bundled fonts"` (add fonts, licences, files).

---

### Task 7: Playback controller and player bar

**Files:**
- Create: `src/classnotes/ui/player.py`
- Test: `tests/test_player.py`

**Interfaces:**
- Consumes: `store.Segment`, `Settings` (Task 1), `theme` object names (Task 6).
- Produces:
  - Pure helpers: `segment_at(segments, t: float) -> int | None` (moved from `segment_view.py`, same behaviour); `line_start(segments, idx) -> int` (ms); `step_line(segments, t: float, delta: int) -> int | None` (index of previous/next line from time t; previous from inside a line more than 1 s in returns that line's own start, like a music player); `RATES = (0.75, 1.0, 1.25, 1.5)`; `step_rate(rate: float, delta: int) -> float` (clamped); `pick_output(devices: list[tuple[str, str]], wanted_id: str, default_id: str) -> tuple[str, bool]` → (device id to use, fell_back) where `devices` is (id, description) and `wanted_id == ""` means Windows default.
  - `class Playback(QObject)` wrapping a `QMediaPlayer` + `QAudioOutput` (injectable for tests): `set_source(path: str | None)`, `set_segments(segs)`, `play()`, `pause()`, `toggle()`, `seek_ms(ms)`, `prev_line()`, `next_line()`, `replay_line()`, `set_rate(rate)`, `set_stop_after_line(on: bool)`, `set_output(device_id: str)`, `outputs() -> list[tuple[str, str]]`; signals `position(int)`, `line_changed(object)` (segment id or None), `playing_changed(bool)`, `status(str)` (e.g. "Headphones unplugged, using Windows default"), `error(str)`. Pitch compensation on. Stop-after-line: when on and position passes the playing line's `end`, pause at `end`. Output: subscribes to `QMediaDevices.audioOutputsChanged`; when the setting is Windows default and the default changed, or the chosen device vanished, re-select via `pick_output` keeping the position.
  - `class PlayerBar(QWidget)` (`objectName "PlayerBar"`): buttons previous, replay, play (primary), next, stop-after-line toggle; times; progress bar with flag ticks (`set_flags(starts_s: list[float], duration_s: float)`), click to seek; speed segmented buttons; output combo ("Windows default" + devices); key labels Space ← → R. Emits user intents; `MainWindow` wires them to `Playback`.

- [ ] **Step 1: Write the failing tests** — pure helpers (`segment_at` cases moved from `test_ui.py`; `step_line` previous inside a line vs at its start, next at the last line → None; `step_rate` clamps at 0.75 and 1.5; `pick_output`: wanted present → (wanted, False), wanted missing → (default, True), wanted "" → (default, False)); `Playback` with a `FakePlayer` (records `setPosition`, `pause`, `setPlaybackRate`; emits `positionChanged` when the test calls `fake.advance(ms)`): stop-after-line pauses at the line end and not when off; `set_rate(1.25)` sets rate and pitch compensation; `prev_line`/`next_line` seek to line starts; changing the fake device list so the chosen device disappears emits `status` and switches to the default without changing position; with no source every action is a no-op.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** (inject `player_factory`/`devices_provider` for tests; production uses `QMediaPlayer`, `QAudioOutput`, `QMediaDevices`). Button icons drawn with `QPainter` paths into `QIcon`s using the ink colour of the current theme.
- [ ] **Step 4: Run** `uv run pytest -q` — PASS. **Step 5: Commit** `git commit -m "feat: playback controller with speed, stop after line and output picker"`.

---

### Task 8: Line list (highlight, follow, edit in place, flags)

**Files:**
- Create: `src/classnotes/ui/line_view.py`
- Delete: `src/classnotes/ui/segment_view.py` (after Task 10 removes its last import; do the delete in Task 10)
- Test: `tests/test_line_view.py`

**Interfaces:**
- Consumes: `flags.flag_reason` (Task 3), `theme.load_fonts` families (Task 6), `store.display_text`.
- Produces: `class LineList(QScrollArea)` (`objectName "LineList"`): `set_segments(segs: list[Segment])`, `update_segment(seg_id: int)` (rebuild one line after an edit/check), `set_playing(seg_id: int | None)`, `scroll_to(seg_id: int)`, `start_edit(seg_id: int) -> bool`, `is_editing() -> bool`, `edit_text() -> str | None`; signals `seek_requested(int)` (line clicked), `edit_saved(int, object)` (seg id, new text or `None` for revert), `edit_started(int)`, `edit_cancelled(int)`, `marked_checked(int)`, `following_changed(bool)`. Each line is a `QFrame` named `Line` with dynamic properties `playing` and `flagged` (re-polished on change); children: time + language label, English `QLabel` (word wrap), Urdu `QLabel` (RTL, Urdu font, word wrap), link row ("Edit translation", "Revert to machine" when edited, "Looks fine" when flagged), flag label "Check: <reason lower-case>", "edited" tag. Recitation lines: Arabic font, "Recitation, not translated", no edit link. Editing swaps the English label for a `QPlainTextEdit` that grows with its content; Enter saves, Shift+Enter inserts a newline, Esc cancels; while editing, clicks on other lines are ignored. Following: `set_playing` scrolls the line into view only while following; a user scroll (wheel or scrollbar drag) turns following off and shows a floating "Back to the playing line" button; clicking it, `scroll_to`, or `set_playing` after a seek from `seek_requested` turns following on. Empty list shows "No speech found."

- [ ] **Step 1: Write the failing tests** (offscreen, `qapp` fixture)

```python
def test_800_lines_open_in_under_a_second(qapp): ...          # build 800 Segments, time set_segments + processEvents, assert < 1.0 s
def test_playing_property_moves_without_rebuilding(qapp): ... # widget ids unchanged after set_playing(1); line 1 has playing=True
def test_edit_enter_saves_shift_enter_newline_esc_cancels(qapp): ...
def test_long_line_edit_saves_whole_text(qapp): ...            # 600-char English, edit, append " end", Enter -> edit_saved text endswith " end" and len 604
def test_flagged_line_shows_reason_and_looks_fine(qapp): ...   # lang_conf .5 -> "Check: language unsure"; click Looks fine -> marked_checked(id)
def test_recitation_has_no_edit_link(qapp): ...
def test_user_scroll_stops_following_and_back_button_resumes(qapp): ...
def test_clicks_on_other_lines_ignored_while_editing(qapp): ...
def test_empty_class_shows_no_speech(qapp): ...
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** If the 800-line test fails, create line widgets lazily as they approach the viewport (placeholder heights estimated from text length), keeping the same interface.
- [ ] **Step 4: Run** `uv run pytest -q` — PASS. **Step 5: Commit** `git commit -m "feat: line list with in-place editing, flags and follow playback"`.

---

### Task 9: Sidebar with search

**Files:**
- Create: `src/classnotes/ui/sidebar.py`
- Test: `tests/test_sidebar.py`

**Interfaces:**
- Consumes: `search.SearchIndex`, `search.Hit` (Task 4), `store.list_library`.
- Produces: `class Sidebar(QWidget)` (`objectName "Sidebar"`): `set_records(records: list[ClassRecord])` (rebuilds the class list and the search index), `select_class(class_id: str | None)` (no signal emitted), `focus_search()`, `add_button`, `settings_button` (public `QPushButton`s; Add a class is the primary); signals `class_selected(str)`, `hit_selected(str, int)` (class id, seg id; `-1` for a title hit). Typing 2+ letters swaps the class list for grouped results (class title header, then rows "mm:ss · snippet" with the match bold); Esc or clearing returns to the class list; re-clicking the already selected class emits `class_selected` again.

- [ ] **Step 1: Write the failing tests** — results appear for "Sunnah" and clicking emits `hit_selected("2026-11-18", id)`; Esc restores the class list; one-letter query keeps the class list; re-clicking the selected class emits again; `select_class` emits nothing.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** (debounce typing by 150 ms with a single-shot `QTimer`). **Step 4: Run** `uv run pytest -q` — PASS.
- [ ] **Step 5: Commit** `git commit -m "feat: sidebar with search across classes"`.

---

### Task 10: Assemble the main window

**Files:**
- Rewrite: `src/classnotes/ui/main_window.py`
- Modify: `src/classnotes/ui/dialogs.py` (Theme combo "Follow Windows / Light / Dark" → `settings.theme`; delete `EditDialog`)
- Delete: `src/classnotes/ui/segment_view.py`
- Modify: `tests/test_ui.py` (drop render-HTML tests; keep and adapt the library, edit-saving, failed-run and live-batching tests to the new widgets)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: everything above. Keeps from today: `MainWindow(settings=None, persist_settings=True)`, `apply_edit(seg_id, text)`, `_save_current()`, `_alert(title, msg)`, `_start(path, day, title, class_id)`, `_finish(...)`, `record`, `record_lib`, `worker`, `library_dir()` (existing tests rely on these).
- Produces: header (`objectName "Header"`): title, meta line "date · length · N lines · K to check" (K live), buttons "Next line to check" (with key label F), "Export" (menu from `export.FORMATS`, each item → save dialog with `export.default_name`, default folder Documents, then `export.export`), "More" (Re-process, Open folder, Locate recording); hidden `#Notice` frame (phase 2 slot); `#Banner` for a missing recording; processing panel restyled; `LineList`; `PlayerBar`. Shortcuts as the spec table via one `keyPressEvent`/`QShortcut` set whose handler returns early when `QApplication.focusWidget()` is a `QLineEdit`, `QTextEdit` or `QPlainTextEdit`, when `LineList.is_editing()`, or when no class is open. Theme: `MainWindow.apply_theme()` re-applies `theme.apply` and re-polishes; called from settings and from the Windows scheme signal; keeps the playing line, scroll position and any edit in progress. Settings persist `playback_rate`, `stop_after_line`, `audio_output` on change. Minimum size 1024x700.

- [ ] **Step 1: Write the failing tests**

```python
def test_space_toggles_play_but_types_in_edit_box(qapp, tmp_path): ...
def test_arrows_r_f_e_shortcuts(qapp, tmp_path): ...             # with a Playback fake: next/prev/replay called; F selects next flagged; E opens editor on playing line
def test_shortcuts_are_noops_without_a_class_or_lines(qapp, tmp_path): ...
def test_export_menu_lists_every_format(qapp, tmp_path): ...      # menu action texts == [label for _, label, _ in FORMATS]
def test_more_menu_has_reprocess_open_folder_locate(qapp, tmp_path): ...
def test_to_check_count_updates_after_edit_and_looks_fine(qapp, tmp_path): ...
def test_missing_recording_disables_player_but_allows_edits(qapp, tmp_path): ...
def test_theme_switch_keeps_edit_and_playing_line(qapp, tmp_path): ...   # start edit, type, apply_theme with dark, edit_text unchanged, playing id unchanged
def test_settings_dialog_theme_round_trip(qapp): ...
def test_clicking_a_line_plays_from_its_start(qapp, tmp_path): ...       # LineList.seek_requested(id) -> Playback.seek_ms(start*1000) and play()
def test_search_result_opens_line_without_playing(qapp, tmp_path): ...   # Sidebar.hit_selected -> record open, line playing-highlighted, Playback.play not called
def test_editing_pauses_and_save_resumes(qapp, tmp_path): ...            # playing -> E pauses; Enter saves and plays again; Esc cancels and plays again
```

(Plus the existing kept tests: library-change edit saving, failed new class, failed re-process, live segments drawn in batches.)

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement**, delete `segment_view.py` and `EditDialog`. **Step 4: Run** `uv run pytest -q` — all PASS.
- [ ] **Step 5: Commit** `git commit -m "feat: new review screen"`.

---

### Task 11: Real-world check and docs

**Files:**
- Modify: `README.md` (Use section: the screen, shortcuts table, Export formats, Theme setting, lines to check)
- Test: whole suite + by hand

- [ ] **Step 1:** `uv run pytest -q` — all pass; record the count.
- [ ] **Step 2:** Launch from the desktop shortcut, open Session 19, and screenshot light and dark (`QWidget.grab()` offscreen script as used before, real fonts). Compare against the drafts; fix spacing or contrast differences.
- [ ] **Step 3: By hand with the user** (cannot be automated): play on the JBL Quantum 300, the speakers and the XV272U monitor; switch the Windows default while playing; unplug the headset; switch Windows light/dark; try 0.75x and 1.5x for pitch; stop after this line. Note results in the hand-over.
- [ ] **Step 4:** Update README. **Step 5: Commit** `git commit -am "docs: review screen, shortcuts, export and themes"`.
