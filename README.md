# Class Notes

A local Windows desktop app that turns Quran-class recordings (taught in Urdu, with the
teacher switching to English at times) into **timestamped English translation notes** —
without an LLM, without uploading anything.

- The teacher's **English is kept exactly as spoken**.
- **Urdu is transcribed, then translated sentence by sentence** (NLLB-200), so the model
  can't summarise or skip across sentences.
- The **original Urdu is kept next to every English line**, so anyone fluent can check it.
- **Quran recitation is detected and marked**, never run through the Urdu translator.
- Click any timestamp to **hear that moment**. Click ✎ to **correct** a line — the machine
  version is always kept alongside your correction.
- Every class is saved as `segments.json` (RAG-ready: timestamps, language, source, English),
  plus `notes.md` and `.srt` subtitles.

## How it works

```
recording ─► Silero VAD (speech spans)
          ─► merge spans with short gaps into blocks (≤ 25 s)
          ─► 8 blocks at a time on the GPU, one Whisper large-v3-turbo encoder pass each:
             language (Urdu / English / Arabic) and transcript from the same pass
          ─► English: kept verbatim
             Urdu:    split sentences ─► NLLB urd_Arab→eng_Latn (one batch per 8 blocks)
             Arabic:  marked as recitation, not translated
          ─► segments.json · notes.md · .srt
```

A 100-minute class takes about 3–4 minutes on an RTX 5060 (it was ~16 minutes before
batching and turbo). Blocks whose output looks repetitive or unsure are redone with the slower
careful decoder, and a block detected as English but written in Urdu script is redone as Urdu.
**Glossary & settings → Speech model** switches back to Whisper large-v3 (about 2–3x slower).

Design: [docs/design.md](docs/design.md) · Plan: [docs/superpowers/plans](docs/superpowers/plans)

## Requirements

- Windows 10/11, an NVIDIA GPU with ≥ 6 GB VRAM recommended (tested on RTX 5060 8 GB).
  Works on CPU too, much slower.
- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 and all packages for you).
- ~8 GB free disk for the models (downloaded once).
- Keep the project in a **short folder path** (e.g. `C:\Projects\QC-VAD-SecondBrain`).
  Windows' 260-character path limit breaks Python packages installed deep inside very long
  paths. If you can't move it, point uv at a short environment folder:
  `set UV_PROJECT_ENVIRONMENT=C:\venvs\classnotes`.

## Setup

```bash
uv sync
uv run python -m classnotes.models
```

The second command downloads Whisper large-v3-turbo (~1.6 GB) and NLLB-200 (~2.5 GB), converts
NLLB to CTranslate2 int8, and stores both in `%LOCALAPPDATA%\ClassNotes\models`. (The app
also does this automatically the first time you process a class.) The conversion runs once in
a throwaway uv environment, so PyTorch never becomes part of the app itself.

Check the GPU works:

```bash
uv run python scripts/smoke_gpu.py
```

## Use

Double-click `run.bat`, or:

```bash
uv run classnotes
```

Or use the **Class Notes** shortcut on the desktop / Start menu
(`powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1` creates it).

Then **Add a class** → pick the recording → date and title → **Process**.
Classes are stored in `Documents\ClassNotes\<date>\`.

### Reviewing a class

The screen is built for listening straight through and stopping to fix lines.

- Click a line to play it. The playing line is boxed and the list follows it; scroll away and
  **Back to the playing line** brings you back.
- **Edit translation** (or **E**) turns the English into a text box where it stands. **Enter**
  saves, **Shift+Enter** adds a new line, **Esc** cancels. Playback pauses while you type and
  carries on after. The machine translation is always kept; **Revert to machine** brings it back.
- **Lines to check** are marked with a reason (language unsure, very short, translation may be
  missing words, words may be misheard, translation unsure). **Next line to check** (**F**) jumps
  to the next one; **Looks fine** clears a mark.
- **Stop after each line** (the button after Next, or **S**) pauses at the end of every line.
- Speed 0.75× to 1.5× keeps the teacher's pitch.
- **Search all classes** (**Ctrl+K**) finds English, Urdu or titles across every class.
- **Export**: Notes (.md), Word (.docx), PDF, Subtitles (.srt), Web subtitles (.vtt), Plain text
  (.txt), Spreadsheet (.csv, opens in Excel with Urdu intact), Data for search tools (.json).
- **More**: Re-process, Open folder, Locate recording.

| Key | Action |
|---|---|
| Space | play / pause |
| ← / → | previous / next line |
| R | replay the playing line |
| S | stop after each line on/off |
| E | edit the playing line |
| F | next line to check |
| [ / ] | slower / faster |
| Ctrl+K | search all classes |

Urdu is shown in Windows' Urdu Typesetting (Nastaliq) font when it is installed
(Settings → Apps → Optional features → *Urdu Supplemental Fonts*), otherwise in Segoe UI.

**Glossary & settings** has:

- **Theme**: Follow Windows (default), Light or Dark.
- **Sound output**: Windows default (follows Windows when you switch devices) or a specific
  speaker or headset. If that one is unplugged, playback falls back to Windows default.

- **Glossary**: words Whisper should expect (surah names, Islamic terms, the teacher's common
  phrases). It biases Whisper toward the right spelling (e.g. ظہر, not زہر "poison").
- **Replace before translating**: `urdu = replacement` lines applied to each Urdu sentence
  before NLLB sees it. The defaults fix mis-spellings found on real class audio
  (حجرت → ہجرت, مشرقین → مشرکین, ختل → قتل, خریب → قریب), keep honorifics
  (حضرت → Hazrat, رسول اللہ ﷺ → Rasulullah (SAW)), and fix phrases NLLB inverts
  (نعوذ باللہ → (God forbid)). The Urdu shown in the notes is never changed.
- Segmentation tuning.

Without the window:

```bash
uv run python -m classnotes.cli "D:/Quran class/2026-11-18.m4a" --title "Al-Kahf 1-10"
```

## Output format

`Documents/ClassNotes/<class_id>/segments.json`

```json
{
  "class_id": "2026-11-18", "title": "...", "date": "2026-11-18",
  "audio_path": "D:/Quran class/2026-11-18.m4a", "duration_s": 3612.4,
  "segments": [
    {"id": 17, "start": 812.4, "end": 829.1, "lang": "ur", "lang_conf": 0.93,
     "source": "…Urdu as transcribed…", "text": "…machine English…",
     "text_edited": null, "surah": null, "topic": null}
  ]
}
```

Re-processing a class keeps the previous file as `segments.<timestamp>.json`.

## Limits

- Machine translation is readable, not polished. Have someone fluent spot-check early classes.
- A sentence that switches language mid-way is treated as Urdu. Short English remarks inside
  Urdu speech stay in that Urdu segment (in English letters) rather than getting their own row.
- Recitation is flagged, but Whisper's Arabic text is not the canonical ayah text.
- NLLB-200 is licensed CC-BY-NC 4.0 (non-commercial). For commercial use, swap in IndicTrans2 (MIT).

## Tests

```bash
uv run pytest
```
