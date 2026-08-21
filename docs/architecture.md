# Architecture

This document covers the sound-design mode (mouth noise → Vital patch) only.
Piano mode ([D6](decisions.md#d6--piano-mode-is-back-in)) is a separate mode
with no vocal query, no Vital preset, and no retrieval — it has no pipeline
here yet, pending the open MIDI-vs-acoustic question.

## The actual problem

Your mouth cannot make a supersaw. When you go "bwaaaow" for a wobble bass,
the audio coming out of you and the audio coming out of Vital are wildly
different signals — different harmonic structure, different noise floor,
different everything. They are alike only in the ways you *meant* them to be
alike: brightness, movement, attack, weight.

So this is not an audio matching problem. It is a **cross-modal retrieval**
problem: two different kinds of sound have to land in the same space, close
together, when a human would say they mean the same thing.

That gap is the project's central risk, the same way "how do notes get into FL"
was the central risk of the old plan. Everything below is arranged around it.

## Pipeline

```
                    ┌─ offline, built once ────────────────────┐
  preset library ──►│ render each patch ──► embed ──► index    │
                    └──────────────────────────────────────────┘
                                                    │
  mouth noise ──► embed ──► search ──► 5 candidates ─┤
                    ▲                        │       │
                    │                        ▼       ▼
              refine loop ◄── you pick / you say "brighter"
                                             │
                                             ▼
                                   write .vital + .mid ──► FL Studio
```

### 1. Corpus build (offline)

- Gather free Vital presets — there are thousands, and preset packs are
  almost always organised into `Bass/`, `Lead/`, `Pad/`, `Pluck/` folders.
  **That folder structure is free role labels**, which lets the search be
  filtered by what you're actually after. Cheap, and a large accuracy win.
- Render every preset headlessly with [DawDreamer](https://github.com/DBraun/DawDreamer),
  which hosts VST3s from Python: load Vital, apply the preset, add a MIDI
  note, render audio. Render two or three variants per preset — a short note
  and a long held one — since attack and sustain carry different information.
- Embed each rendering. Store preset file, rendered audio, embedding, role
  tag, and the parsed JSON parameters side by side.

This is a batch job that runs overnight and rarely changes. Everything at
query time is a fast lookup against it.

### 2. Query embedding — the hard part

Ranked by effort, and intended to be built in this order:

**a. Domain-normalised timbral features.** Brightness (spectral centroid),
noisiness, attack time, decay shape, harmonicity, spectral flux. Crude — but
z-score the vocal queries against a corpus of vocal queries and the presets
against the preset corpus, and "the brightest sound I can make" starts
matching "a bright preset" even though their absolute numbers are nothing
alike. Interpretable, and the same features become the nudge axes later.

**b. CLAP embeddings.** [CLAP](https://github.com/LAION-AI/CLAP) puts audio
*and text* into one shared space. This is the highest-leverage component in
the whole project, because it solves two requirements at once: vocal queries
and word-based search land in the same space with one model, no training.
Start here for real.

**c. Fine-tune on vocal imitation data.** The
[VocalSketch dataset](https://github.com/interactiveaudiolab/VocalSketchDataSet)
contains 40 commercial-synthesizer and 40 single-synthesizer reference sounds,
each with roughly ten crowd-sourced vocal imitations — directly on-point
training data. [Vocal Imitation Set](https://github.com/interactiveaudiolab/VocalImitationSet)
is larger and broader. A shared encoder trained with a contrastive loss pulls
imitation and reference together.

**d. Personalise on your own imitations.** Every time you accept a candidate,
you have created a labelled pair: *this noise you made* → *that patch you
meant*. Those pairs accumulate for free from ordinary use, and they are worth
more than any public dataset, because the system only ever has to understand
one person's mouth. This is the feature that compounds.

### 3. Refinement

Two mechanisms, because "brighter" and "warmer, kind of hollow" are different
kinds of request:

**Parameter nudges — for words that name a real axis.** "Brighter" → filter
cutoff up. "More wobble" → LFO rate and depth to filter. "Shorter tail" →
release down. "Dirtier" → drive up. Because a `.vital` preset is JSON, these
are direct, predictable, reversible edits to named fields. A small mapping
table covers most of what gets asked; a language model handles phrasing
variants and maps them onto that table rather than inventing parameter values.

**Vector nudges — for vague words and for picking.** Move the query embedding
toward what you chose and away from what you rejected, then search again.
This is textbook relevance feedback, it is a dozen lines of code, and it works
disproportionately well. CLAP's shared space means a text phrase can push the
query vector the same way a chosen candidate can.

Picking from five candidates is not a fallback for when words fail — it is
usually the faster interaction, and it is also what quietly generates the
personalisation training data from step 2d.

### 4. Notes from the same take

The recording is analysed twice, independently:

- **Timbre path** — everything above.
- **Pitch and rhythm path** — onsets, pitch contour, energy envelope → a MIDI
  pattern.

An important nuance: when you vocalise a sound you are expressing *rhythm and
rough contour*, not a precise melody. So this path should be deliberately
more forgiving than a transcription tool — snap hard to the grid, snap hard to
a scale, prefer few confident notes over many uncertain ones. Being
approximately right and clean beats being precisely right and messy, because
the pattern is a starting point you'll edit anyway.

### 5. Output

The app is standalone; the patch reaches FL Studio as a file. That's not a
compromise — it's how every preset pack works, and it keeps the result yours
to edit afterwards.

- Write a `.vital` preset file **directly into Vital's user preset folder**, so
  it simply appears in Vital's browser inside FL. No importing, no file
  wrangling — one click from noise to loaded patch.
- Also write a copy next to the project for keeping and sharing.
- Write a `.mid` for the pattern.
- Later, the direct FL routes: virtual MIDI via loopMIDI, and FL 21.1+'s
  Python piano-roll scripting.

## Why retrieve-then-nudge, and not solve from scratch

Solving synth parameters directly from a target sound — what Synplant 2's
Genopatch does — has the higher ceiling. It was not chosen for v1 because:

1. **It always returns something usable.** A retrieved preset was built by a
   human who knew what they were doing. A solver can return a patch that
   technically matches and is musically useless.
2. **It's fast.** Nearest-neighbour search over a pre-built index is instant.
   Parameter search is a slow optimisation loop.
3. **It degrades gracefully.** A mediocre retrieval still hands you five
   real patches to start from, which is already better than scrolling a
   preset browser blind.

The honest cost: **retrieval can only find what's in the library.** If nothing
in the corpus resembles what's in your head, search cannot conjure it. That
ceiling is exactly what a parameter solver would raise later, and it is the
main reason to keep the door open.

## Stack

| Layer | Choice | Why |
| --- | --- | --- |
| Core | Python | Audio ML, embeddings, and DawDreamer all live here |
| Plugin hosting | DawDreamer | Loads Vital headlessly, sets parameters, renders audio, saves/loads state — the whole corpus build depends on it |
| Embeddings | CLAP, via ONNX Runtime | Shared audio+text space; ONNX keeps PyTorch out of the shipped build |
| Search | FAISS or brute-force NumPy | A few thousand presets doesn't need anything clever; brute force is fine until it isn't |
| Presets | `.vital` JSON, read and written directly | The reason Vital was chosen |
| MIDI | `mido` + `python-rtmidi` | File export now, virtual port later |
| UI | Web frontend over a local socket | Auditioning candidates is the core interaction — needs fast playback and A/B |
