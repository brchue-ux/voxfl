# Roadmap

From word-dump to finished product, in six phases. Each phase ends with a
**exit criterion** — something demonstrable. If a phase cannot meet its exit
criterion, that is the signal to change the plan, not to push on.

Sizing is in *sessions* (one focused half-day, solo, AI-assisted). Treat them
as relative weights, not promises.

---

## Phase 0 — Kill the unknown  ·  1–2 sessions

The README said the central open question was how content gets into FL Studio.
Answer it with working code before designing anything else. No UI, no polish,
one throwaway script.

- [ ] Record 4 bars of humming to a `.wav` from the command line
- [ ] Run it through Basic Pitch, write a `.mid`
- [ ] Drag that `.mid` into FL Studio, confirm notes land in the piano roll
- [ ] Install loopMIDI, send a scripted note from Python, confirm FL receives
      and records it
- [ ] Check what your FL edition already ships (Newtone, Edison's convert-to-
      score) and how good it is — you need to know your real baseline
- [ ] Confirm your FL version supports piano-roll Python scripting (21.1+)

**Exit criterion:** a melody you hummed exists as editable notes in an FL
piano roll, arrived at two different ways. Screenshot both.

**Why this first:** it converts the project's biggest risk into a known
quantity in a day, and it produces something genuinely useful immediately —
even the ugly script version is a working tool.

---

## Phase 1 — Conversion engine + evaluation harness  ·  4–6 sessions

The phase where the tool becomes *accurate*. No UI yet; this is a library plus
a test rig. See [evaluation.md](evaluation.md) for the measurement design.

- [ ] Record the reference set: 30–50 takes of your own humming across tempos,
      registers, and levels of sloppiness
- [ ] Hand-correct each into ground-truth MIDI (tedious, unavoidable, the
      single highest-leverage asset in the project)
- [ ] Build the metrics harness: onset F1, pitch accuracy, note-count delta
- [ ] Measure Basic Pitch end-to-end as the baseline to beat
- [ ] Implement the analysis/interpretation split from
      [architecture.md](architecture.md)
- [ ] Bake off pitch trackers on the reference set; pick by number, not vibe
- [ ] Build the parameter sweep and tune interpretation defaults

**Exit criterion:** the pipeline beats the Basic Pitch baseline on your own
reference set, and a typical 4-bar take needs fewer than ~10 manual edits in
FL to be usable. Set the hard numeric targets *after* seeing the baseline —
inventing them now would be theatre.

---

## Phase 2 — The app  ·  6–8 sessions

The first thing that is a product rather than a script.

- [ ] Windows desktop shell, Python core behind a local socket
- [ ] Pre-record controls: tempo, bars, key, count-in
- [ ] Record button with metronome and level meter
- [ ] Piano-roll preview of the result
- [ ] Live interpretation controls — quantize strength, scale snap, sensitivity,
      octave — all re-deriving instantly from the cached analysis
- [ ] Take history: every recording kept, re-convertible, never lost
- [ ] Output: Export `.mid`, auto-save to watched folder, Send to FL (Route B)
- [ ] **FL Studio setup wizard** — detect/install loopMIDI, create the port,
      walk through FL's MIDI settings with screenshots
- [ ] Packaged installer, tested on a clean Windows machine

**Exit criterion:** from a cold start, idea in your head to notes in FL in
under 60 seconds, without touching a terminal. Someone who is not you can
install it and get a melody in without being told how.

**Watch out:** the setup wizard is not polish, it is the product. A tool that
needs a driver install and a DAW settings change has already lost most users
before its first note.

---

## Phase 3 — Beatbox → drums  ·  5–7 sessions

Different problem: classification, not pitch. Onsets are easy, telling a kick
from a snare is not — and everyone's mouth sounds are different, so a general
model will always disappoint. Personalisation is not a feature here, it is the
only way this works.

- [ ] Onset detection tuned for percussive transients
- [ ] Segment each onset into a short window; mel-spectrogram features
- [ ] Ship a general classifier (kick / snare / closed hat / open hat / clap)
- [ ] **Train your kit**: record ~8 examples of each of your own sounds, then
      personalise via embedding + nearest-neighbour or a fine-tuned final layer
- [ ] Flag inconsistent training takes rather than silently learning noise
- [ ] Velocity from onset energy; preserve micro-timing via quantize strength
- [ ] Map to GM drum notes and to FPC, with a user-editable mapping

Prior research worth reading first: the Amateur Vocal Percussion dataset
([arXiv:2009.11737](https://arxiv.org/pdf/2009.11737)) and user-personalised
classification via deep embeddings
([arXiv:2204.04646](https://arxiv.org/pdf/2204.04646)) — the second is
precisely this problem.

**Exit criterion:** after training on your own sounds, ≥90 % hit
classification on a held-out set of your beatboxing.

---

## Phase 4 — The AI editing layer  ·  4–5 sessions

This is where an LLM belongs — **not** in transcription. Transcription is a
signal-processing problem and a language model makes it worse. Editing a
pattern is a language problem and a language model makes it better.

Because everything is already the JSON IR, this phase is mostly prompt and
schema work rather than new architecture.

- [ ] Expose the IR to the model; constrain output to a validated edit schema
- [ ] Support the commands that actually come up: "make the hats triplets",
      "double-time this", "add a variation for bar 4", "harmonise a third
      above", "make this fit F minor", "make it swing"
- [ ] Preview-and-accept, never silent mutation; full undo
- [ ] Non-LLM generators alongside it: humanisation, fills, simple variations —
      cheaper, instant, and deterministic

**Exit criterion:** ten canned commands applied to a reference pattern produce
musically correct results reliably, with schema validation catching bad output
rather than corrupting patterns.

---

## Phase 5 — Deep FL integration and release  ·  4–6 sessions

- [ ] Route C: bundled FL piano-roll Python script that places notes into the
      open piano roll directly
- [ ] First-run experience, auto-update, crash/error reporting
- [ ] Decide the shape: personal tool, free release, open source, or paid
- [ ] If releasing: a landing page whose hero is a 20-second video of a hum
      becoming a pattern. This category sells entirely on that demo.

**Exit criterion:** v1.0 installer that a stranger can use end to end.

---

## Definition of done for v1.0

A Windows app that records a vocal take, converts humming to a melody and
beatboxing to a drum pattern, lets you fix it with sliders and plain English,
and puts the result in FL Studio three different ways. Offline. No account.

## Later, explicitly not now

- **Live / real-time mode.** Deferred on purpose — it is strictly harder and
  strictly less accurate, and Phase 1's engine is the prerequisite for doing
  it well. Revisit after v1.0.
- **Piano mode** (the README's second idea). Real-time piano in, AI suggests
  continuations. A different product sharing only the IR and output layers.
  Do not let it dilute v1.
- **Polyphony.** One voice, one note at a time. Chord detection from humming
  is a research problem, not a feature.
- **VST/plugin version.**

## Risk register

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Crowded market — Dubler 2, DubBox, imitone, Waves OVox all exist | High | Compete on FL-native workflow and language editing, not on pitch tracking. Decide early whether this is a personal tool (where "it fits my workflow" is enough) or a product (where the wedge must be sharp). See [decisions.md](decisions.md#positioning) |
| FL already ships audio→MIDI (Newtone, Edison) | High | Verify its real quality in Phase 0. Beat it on *workflow speed*, not transcription accuracy |
| Your humming is out of tune and drifts | Medium | Scale snapping and quantize strength matter more than tracker accuracy. This is why interpretation is tunable and re-runnable |
| loopMIDI driver install kills onboarding | Medium | Route A (plain `.mid`) always works with zero setup; wizard for Route B |
| Scope creep into "AI writes my song" | Medium | It is a capture tool. Generation is Phase 4 editing only, on patterns you sang |
| FL piano-roll scripting API can't do what's needed | Low | Route C is scheduled last precisely so nothing depends on it |
| Solo-project motivation decay | Medium | Phase 0 delivers a usable thing in a day; every phase after ships something you personally use |

## Suggested order of attack

Phase 0 this week. It is small, it retires the biggest unknown, and you end it
with a working — if ugly — hum-to-FL pipeline. Everything after that is
improvement on something real, which is a much better position than designing
against an unknown.
