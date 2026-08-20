# Architecture

## The one idea that shapes everything

**Separate analysis from interpretation.**

- **Analysis** runs once per recorded take. It is expensive (ML inference) and
  produces a *continuous description* of the audio: a pitch curve, an energy
  curve, and a list of onsets. It never decides what a "note" is.
- **Interpretation** turns that description into discrete notes. It is pure,
  cheap arithmetic, and it re-runs from scratch every time you move a slider.

Why this matters, concretely:

1. **The UI feels instant.** Change quantize strength, key, or sensitivity and
   the piano roll updates in milliseconds — no re-recording, no re-inference.
2. **The eval harness can sweep parameters.** Analyse the whole test set once,
   then try 500 interpretation settings against it in seconds. Without this,
   tuning is guesswork.
3. **Bad takes stay recoverable.** The raw analysis is kept, so a take that
   converted badly can be re-interpreted rather than re-sung.

Almost every "voice to MIDI" tool fuses these two steps because it is
real-time and has no choice. Take-based conversion is what buys us the split —
it is the main structural advantage of the decision to not go real-time.

## Pipeline

```
mic ──► capture ──► analysis ─────────────► interpretation ──► IR ──► output
                    (once per take)         (every param change)
```

### 1. Capture
- WASAPI input via `sounddevice` (PortAudio). Shared mode is fine; take-based
  conversion has no latency requirement, which sidesteps ASIO entirely.
- Mono, 22.05 kHz internally (pitch trackers want this, not 48 kHz).
- Count-in metronome at the user-set tempo, fixed bar length. Knowing the
  tempo and bar count *before* recording removes the hardest inference problem
  in the whole system. Do not try to be clever here.
- Always keep the raw take on disk. It is the input to every later re-run and
  to the test set.

### 2. Analysis (once per take)
- **Pitch**: fundamental frequency curve + per-frame confidence.
- **Onsets**: note-start candidates with strength.
- **Energy**: RMS envelope, used later for velocity.
- Pre-processing: DC removal, high-pass ~70 Hz, noise gate calibrated from a
  one-second room-tone sample taken at first run.

Candidate trackers, to be benchmarked in Phase 1 rather than chosen now:

| Tool | Notes |
| --- | --- |
| `pYIN` (librosa) | Monophonic, well understood, no model download, CPU-cheap |
| CREPE | Deep model, typically the most accurate on messy input, heavier |
| Basic Pitch (Spotify) | Apache-2.0, does pitch *and* note segmentation in one shot; strongest baseline to beat |

Basic Pitch is polyphonic and end-to-end, so it can serve as a whole-pipeline
baseline *and* as a component. Start by measuring it as the baseline: if our
custom pipeline cannot beat it, use it and spend the time elsewhere.

### 3. Interpretation (every parameter change)
Ordered, each step independently testable:

1. **Voicing** — gate frames by pitch confidence and energy; drop breath noise.
2. **Note formation** — segment the pitch curve into notes at onsets and at
   sustained pitch changes. Handle the three things humming does that
   instruments do not: scoops into pitch, vibrato, and glissando between notes.
3. **Pitch quantization** — median pitch per note → nearest semitone; then
   optional snap to a scale (user-chosen key, or detected from the take).
4. **Time quantization** — snap to grid with an adjustable *strength* (0 % =
   raw human timing, 100 % = dead on grid) so groove survives.
5. **Cleanup** — merge notes shorter than a threshold into their neighbour,
   drop orphan blips, enforce monophony (no overlaps).
6. **Velocity** — map the energy envelope onto 1–127 with a curve.

### 4. Intermediate representation (IR)
One plain JSON structure — tempo, time signature, key, and a note list of
`{start_ticks, duration_ticks, pitch, velocity}`.

Everything downstream consumes only the IR: the piano-roll preview, the MIDI
writer, the virtual-port player, and the natural-language editing layer in
Phase 4. Because the IR is small, plain text, and schema-checked, an LLM can
read and rewrite it directly, and every edit it proposes can be validated
before it is applied. That is what makes Phase 4 cheap instead of a rewrite.

### 5. Output
See below.

## Getting notes into FL Studio

This was the README's "central open technical question". It is not actually
open — there are three working routes with very different risk profiles.

### Route A — MIDI file (ship this first)
Write a `.mid`, drag it into FL Studio's playlist or channel rack. Also write
every export to a watched folder so the file is always one drag away.

Risk: none. Works on every FL edition, every version. This alone makes the
tool useful, and it is the whole of Phase 0's output.

### Route B — Virtual MIDI port (best feel)
Create a virtual MIDI cable with **loopMIDI** (free, Windows). The app plays
the IR out of that port; FL Studio sees it as a MIDI input device and records
it into the piano roll like any controller.

Risk: low, but it is a third-party driver install — meaning it is also the
single biggest onboarding cliff in the product. Budget real time for a setup
wizard that detects loopMIDI, offers to install it, creates the port, and
walks through FL's MIDI settings. Tools like this die at exactly this step.

### Route C — FL Studio piano-roll script (deepest integration)
FL Studio 21.1 and later support **Python scripts in the piano roll**. A
script can generate and modify notes in the currently open piano roll. The
plan: the app writes the IR to a known path, and a small bundled FL script
reads it and places the notes directly — no file, no drag, no MIDI recording.

Risk: medium and FL-specific. The scripting API's exact capabilities need
hands-on verification before anything depends on it. Deliberately scheduled
last, as an enhancement to a product that already works without it.

### Rejected
- **Writing `.flp` project files directly** (e.g. via PyFLP) — the format is
  proprietary and reverse-engineered. Corrupting a user's project is an
  unacceptable failure mode for a convenience tool.
- **VST3 plugin via JUCE** — the "native" answer, but it means C++, plugin
  formats, and awkward host MIDI-output routing. Revisit only if this becomes
  a commercial product.

## Stack

| Layer | Choice | Why |
| --- | --- | --- |
| Audio + ML core | Python | Every pitch tracker, onset detector, and MIR library lives here. This is the hard part; do it where the tools are. |
| Inference runtime | ONNX Runtime | Keeps PyTorch out of the shipped build — a much smaller installer. |
| MIDI | `mido` + `python-rtmidi` | File writing and virtual-port output from one library pair. |
| Audio I/O | `sounddevice` | PortAudio/WASAPI, straightforward on Windows. |
| UI | Web frontend in a local shell | A piano roll is a canvas widget; the web platform is the fastest place to build one. |
| Packaging | PyInstaller → single installer | One `.exe`, no Python install for the user. |

The UI shell (pywebview vs Tauri vs Electron) is deliberately left open until
Phase 2 — it is a swap-out decision, not a foundation, as long as the frontend
talks to the Python core over a local socket rather than being fused to it.
