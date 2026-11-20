# Review screen (phase 1): design

Date: 2026-11-20 · Status: draft for approval · Visual reference: `docs/design/drafts/a-reader.html`

## Intent

The person reviewing a class **listens straight through and stops to fix lines**. The screen exists
to keep their eyes on the line being played, make a fix take seconds, tell them which lines most
need checking, and play on whatever speaker or headset they use. Today the window is a rich-text
list with a dialog for every edit, no speed control, no shortcuts, a player that sticks to the
sound output that was default at launch, and two separate export buttons.

## Goals

1. A new native Qt review screen laid out like draft A (one column of lines, the playing line
   boxed, a player bar at the bottom), with two extras the user picked: the **sound output picker**
   from draft B and **stop after this line** from draft C.
2. **Player:** play/pause, previous/next line, replay line, stop after this line, speed 0.75x / 1x /
   1.25x / 1.5x with the voice pitch kept, a progress bar showing where the lines to check are.
3. **Keyboard shortcuts** for everything a listener does without reaching for the mouse.
4. **Edit in place:** the English line turns into a text box where it stands.
5. **Lines to check:** each line that is likely wrong is marked with a short reason; "Next line to
   check" jumps to it; a line can be marked as checked.
6. **Search across all classes** from the sidebar.
7. **One Export button** offering every format.
8. **Sound works on every output** the PC has, including after Windows switches its default.
9. **Light and dark themes that follow Windows** by default, with a setting to choose Light, Dark
   or Follow Windows (added by the user during design).

## Non-goals (this phase)

- Learning from edits (phase 2) and Quran matching (phase 3). This phase only leaves room for
  them: a notice bar above the list (phase 2 will offer "use Sunnah from now on" there) and a
  card slot under a line (phase 3 will show the matched ayah there).
- Processing a folder of recordings overnight (later). English audio (dropped).

## Anti-goals (a failure even if it works)

- An embedded web page (`QWebEngineView`). Drafts are inspiration only; the screen is Qt widgets.
- Changing the stored machine translation. Edits stay in `text_edited`; the machine text is kept.
- Flags that cry wolf. If a third of the lines are flagged, nobody checks any. Target: about 5 to 10%
  of a class's lines.
- A shortcut firing while the user types (Space in the edit box must type a space).
- Slower playback that changes the teacher's pitch.

## Constraints

- PySide6 6.12 (Qt 6.12), Windows 10/11, fully offline. Pitch compensation is available
  (`QMediaPlayer.setPitchCompensation`, reported Available on this PC).
- Fonts are bundled with the app (all SIL OFL): Familjen Grotesk (interface), IBM Plex Mono (times,
  keys), Noto Nastaliq Urdu (Urdu lines), Noto Naskh Arabic (Arabic). Licence files go next to the
  fonts. Loaded with
  `QFontDatabase.addApplicationFont`; Windows' own "Urdu Typesetting" is the fallback.
- Existing classes (`schema_version` 1) must open unchanged; new fields are optional.
- Tests run offscreen (`QT_QPA_PLATFORM=offscreen`); real sound output is checked by hand.

## Approaches (for drawing the list of lines)

1. **Keep `QTextBrowser` rich text** (today). Cheapest, but buttons per line, hover states, flags and
   editing in place are not possible; every edit needs a dialog. Rejected: fails goal 4.
2. **`QListView` with a painted delegate** (model/view). Scales to any length and scrolls
   smoothly, but every line is hand-painted: wrapped right-to-left Nastaliq, links, the flag, and
   later the Quran card all need custom painting and hit-testing. Most code, slowest to change.
3. **A scroll area with one small widget per line** (labels for English and Urdu, a link row, a
   flag; the English label swaps for a text box when editing), styled with one QSS file. Closest to
   the draft, simplest to build and change, and phase 2/3 slots are ordinary widgets. Risk: a long
   class means many widgets.

**Chosen: 3** (my call, as the how was handed over). Guard: a class of 800 lines must open in under
1 second and window resizing must stay smooth. If the measurement fails, build line widgets only as
they scroll into view (the data model does not change).

## The screen

```
┌ sidebar 280 ─────────┬ header: title · date · length · lines · "N to check" ──────────────────┐
│ Class Notes          │                          [Next line to check  F] [Export ▾]            │
│ [Search all classes ]├─ notice bar (phase 2 slot, hidden in phase 1) ────────────────────────┤
│ Classes              │  42:55  Emotionally, my father is going to leave me...                  │
│  Session 19 · ...    │  Urdu   ایموشن کی بھئی میرے والد...                    Edit translation  │
│                      │ ┌──────────────────────────────────────────────────────────────────┐   │
│                      │ │45:05 And to experience the love of the Messenger... (playing)     │   │
│                      │ │      اور اپنی day-to-day life میں ...                               │   │
│ [Add a class]        │ └──────────────────────────────────────────────────────────────────┘   │
│ [Glossary, settings] │  45:42  It is.          ● Check: one word, language unsure  Looks fine  │
├──────────────────────┴─────────────────────────────────────────────────────────────────────────┤
│ ⏮ ↺ ▶ ⏭ [■ Stop after line]  45:05 ━━━━━━━│━━━━━━━━━━ 1:42:34  [0.75 1 1.25 1.5]  [Output ▾] │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Line:** time (mono 13px) and language label on the left; English 17px; Urdu below, right to
  left, Nastaliq 19px; a row of quiet links ("Edit translation", "Revert to machine" on edited
  lines, "Looks fine" on flagged lines). Edited lines say "edited". Recitation lines show the Arabic
  and "Recitation, not translated", with no edit link.
- **Playing line:** a white box with a 1px border on the grey page, its time in the accent colour.
  The highlight moves without rebuilding the list.
- **Following playback:** the list keeps the playing line in view. When the user scrolls away,
  following pauses and a "Back to the playing line" button appears; clicking it, or any jump by
  shortcut or click, resumes following.
- **Clicking a line** plays from its start. Clicking a link does not.
- **Processing a new class:** the current processing panel (status, progress, Cancel) restyled to
  the new look; lines appear in the list as they are made.
- **Window:** minimum 1024x700.

### Visual system (from draft A)

Light tokens (draft A): page `#f8f8f8`, surface `#eeeeee`, panel `#ffffff`, ink `#0a0a0a`, accent
`#1f6b3a`, muted `#5b5f5c`, hairline ink at 13%, flag dot `#b26b00` with label `#7a4b00`.

Dark tokens (draft B): page `#161c1a`, surface `#1f2725`, panel `#26302d`, ink `#e3e2da`, accent
`#9fc7b8` (its button label `#13201b`), muted `#a3a89f`, hairline ink at 12%, flag dot `#e0a84f`
with label `#e8bd73`. Every text/ground pair meets the same contrast as the light theme (body text
7:1, labels 4.5:1); the builder checks each pair.

**Theme choice:** Settings has "Theme: Follow Windows (default) / Light / Dark". Follow Windows
reads `QGuiApplication.styleHints().colorScheme()` and switches live on `colorSchemeChanged`,
without restarting or losing the playing position. Both themes come from the same token names, so
one QSS template serves both.

Radius 8 (controls),
12 (panels), 20 (frames). Spacing 4, 8, 12, 16, 24, 32, 48. Text people read is 16px or more;
labels 13px weight 500; sentence case; no capitals-only labels. One filled button per view (the
accent, for the main action); every other button is the outlined secondary; links are text links.
Hover: buttons step up 1px and press down; lines get a faint background. All tokens live in one
place and the QSS is generated from them.

## Player

- Play/pause; previous and next line jump to that line's start; replay line jumps to the start of
  the playing line.
- **Stop after this line:** a toggle. While on, playback pauses at the end of each line, so the
  user can listen line by line and fix as they go. Stays on until turned off; remembered.
- **Speed:** 0.75x, 1x, 1.25x, 1.5x, pitch kept; remembered between sessions.
- **Progress bar:** click to seek; small amber ticks mark lines to check.
- **Sound output picker:** "Windows default" plus each output by name (on this PC: JBL Quantum 300,
  the speakers, the XV272U monitor). See Sound output.

## Shortcuts

Active whenever the focus is not in a text field:

| Key | Action |
|---|---|
| Space | play / pause |
| ← / → | previous / next line |
| R | replay the playing line |
| S | stop after this line on/off |
| E | edit the playing line |
| F | next line to check |
| [ / ] | slower / faster |
| Ctrl+K | search all classes |

In the edit box: Enter saves, Shift+Enter starts a new line, Esc cancels. In search: Esc clears.
The player bar shows the main keys as small key labels.

## Editing in place

"Edit translation" or E turns the English label into a text box of the same width, filled with the
current English (the edit if there is one). Playback pauses while editing and resumes after saving
if it was playing. Save writes `text_edited` and saves the class (same rules as today: into the
class's own library, retry through file locks, never lose the edit). "Revert to machine" clears
`text_edited`. Phase 2 hooks in after a save.

## Lines to check

A line is flagged when any signal fires, and shows the first reason in plain words:

| Signal | Reason shown | Source |
|---|---|---|
| Language detection below 0.9 | Language unsure | `lang_conf` (all classes) |
| Two words or fewer in the Urdu | Very short, may be noise | `source` |
| English much shorter than the Urdu (word ratio below a calibrated cut-off) | Translation may be missing words | `source`, `text` |
| Whisper's average log-probability below a calibrated cut-off | Words may be misheard | new `asr_logprob` (new runs only) |
| NLLB's score below a calibrated cut-off | Translation unsure | new `mt_score` (new runs only) |

- Never flagged: edited lines, lines marked "Looks fine" (new `checked` field), recitation.
- Cut-offs are calibrated on Session 19 so roughly 5 to 10% of lines are flagged, and kept in one
  place in code.
- The header shows "N to check"; "Next line to check" (F) jumps to the next one after the playing
  line, wrapping round.

## Search across classes

- The sidebar field (Ctrl+K). From two characters on, the class list is replaced by results grouped
  by class: time, and a one-line snippet with the match in bold.
- Searches the English (edit and machine), the Urdu, and class titles. Case-insensitive; Urdu and
  Arabic vowel marks are ignored when matching.
- Clicking a result opens that class and scrolls to the line, making it the current line without
  starting playback. Esc or clearing the field brings the class list back.
- All classes' lines are read into memory when the library loads (a few hundred kilobytes per
  class) and searched directly; no index file.

## Export

One **Export** button opens a menu; each item opens a save dialog named
`<class_id> <title>.<ext>`, defaulting to Documents. English means the edit where there is one.

| Item | File | Contents |
|---|---|---|
| Notes | .md | as today's notes.md: time, English, Urdu, recitation marked |
| Word document | .docx | title, date, then each line: time, English, Urdu right to left in the Urdu font |
| PDF | .pdf | the same layout as the Word document, via Qt's PDF writer with the bundled fonts |
| Subtitles | .srt | as today |
| Web subtitles | .vtt | the same cues in WebVTT |
| Plain text | .txt | `[mm:ss] English`, one line each |
| Spreadsheet | .csv | start, end, language, Urdu, English (machine), English (edited), flag reason (UTF-8 with BOM so Excel shows Urdu) |
| Data for search tools | .json | the class's segments.json as stored |

New dependency: `python-docx` (MIT) for Word.

## Sound output

- **Cause found:** the player is bound to the output that was Windows' default when the app opened
  (on this PC the default is currently the XV272U monitor over HDMI). Switching the default later,
  or plugging in a headset, is not followed.
- **Fix:** the picker in the player bar. "Windows default" follows Windows: when the default changes
  (`QMediaDevices.audioOutputsChanged`), the player moves to the new default and keeps its position.
  Picking a named output uses that one and is remembered. If a remembered output is unplugged, the
  player falls back to Windows default and says so in the status line.
- If playback reports an error, the player shows it with "Try another output" next to the picker.

## Data changes

- `Segment`: `asr_logprob: float | None = None`, `mt_score: float | None = None`,
  `checked: bool = False`. `schema_version` becomes 2. Version 1 files load with the defaults.
- `Settings`: `audio_output: str = ""` (device id; empty means Windows default),
  `playback_rate: float = 1.0`, `stop_after_line: bool = False`,
  `theme: str = "system"` (`"system" | "light" | "dark"`).
- The pipeline stores `asr_logprob` per block (from the batch result already computed) and
  `mt_score` per Urdu segment (NLLB `return_scores`, averaged over its sentences).

## Testing

- Offscreen Qt tests: every shortcut (and that none fire inside the edit box), edit save / cancel /
  revert, stop after this line, speed steps, flag rules and counts, next line to check wrap-round,
  search matching (Urdu marks ignored) and opening a result, each export format written and read
  back, sound output fallback with a fake device list, schema 1 files loading, theme switching
  (setting and a simulated Windows change) restyling without losing the playing line.
- Performance test: an 800-line class opens in under 1 second.
- By hand: playback on all three outputs, switching the Windows default while playing, unplugging
  the headset, switching Windows between light and dark mode.

## Settled during review (my calls)

- **Where today's other actions go:** a "More" menu beside Export holds Re-process, Open folder and
  Locate recording. The missing-recording banner stays, restyled, above the list.
- **Arabic text** (recitation lines now, Quran text later) uses Noto Naskh Arabic (OFL, bundled),
  not the Urdu Nastaliq face.
- **Counts stay live:** "N to check" and the progress-bar ticks update after every edit, "Looks
  fine" and revert.
- **Settings dialog** keeps its fields, plus Theme, and takes the new look.
- **While editing,** clicking another line or pressing a playback shortcut does nothing until the
  edit is saved or cancelled.

## Left to the builder

File and widget structure, QSS details beyond the tokens, the exact cut-off numbers after
calibration, Word/PDF styling details, icon drawing for the player buttons.
