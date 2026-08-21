# Roadmap

Six phases, roughly 27 sessions. Phases 0 and 1 run in a terminal because
they are experiments; from Phase 2 onward this is a desktop app. A session is one focused half-day, solo,
AI-assisted — relative weights, not promises. Each phase ends in a
demonstrable **exit criterion**; a phase that can't meet its criterion is a
signal to change the plan, not to push on.

---

## Phase 0 — Prove the corpus loop  ·  1–2 sessions

Everything depends on two mechanical abilities. Confirm both before designing
anything else.

- [ ] Install Vital; collect a few hundred free presets
- [ ] Get DawDreamer hosting Vital headlessly: load a preset, add a MIDI note,
      render to `.wav`
- [ ] Open a `.vital` file, confirm it's readable JSON, find the filter cutoff
- [ ] Change that value, write the file back, confirm Vital opens it and
      sounds different
- [ ] Batch-render 100 presets unattended; note how long it takes

**Exit criterion:** you can render a preset library to audio from a script,
and author a modified patch that Vital loads. Both verified by ear.

**Why first:** these are the two assumptions the entire architecture rests on.
If DawDreamer can't host Vital reliably, or the JSON turns out to be opaque,
the plan changes completely — and you want to know that on day one, not in
week six. This is the equivalent of the old plan's "can I get notes into FL".

---

## Phase 1 — Retrieval that actually works  ·  4–6 sessions

The research risk, isolated and measured. Still no interface — a script and
a scoreboard. Phases 0 and 1 are the *only* headless ones; Phase 2 builds the
real UI, and the product lives there.

- [ ] Build the personal benchmark: pick ~50 presets across bass/lead/pad/
      pluck, listen to each, record yourself imitating it, label the pair.
      Half a day of work, and it makes everything after it measurable
- [ ] Render and embed the full corpus; tag roles from preset folder names
- [ ] Baselines in order: random, hand-crafted timbral features with domain
      normalisation, then CLAP
- [ ] Add role filtering — searching only basses when you want a bass is a
      large, nearly free accuracy win
- [ ] Measure Recall@1, Recall@5, Recall@20 and MRR against the benchmark

**Exit criterion:** the preset you were imitating lands in the top 5 more
often than not, within its role. Set the harder targets after seeing the CLAP
baseline rather than inventing them now.

**If it fails:** this is the phase where the project can genuinely die. If
CLAP plus normalisation plus role filtering can't beat chance meaningfully,
the honest options are fine-tuning on VocalSketch (Phase 3's technique, pulled
forward) or narrowing the product to word-search only and dropping the vocal
query. Decide on evidence, not stubbornness.

---

## Phase 2 — The loop that makes it usable  ·  5–7 sessions

Retrieval being merely decent is fine if correcting it is fast. This phase is
where the product lives.

- [ ] Record button, role selector, instant results
- [ ] Five candidates, auditioned on one keypress each, A/B against each other
- [ ] Pick one → re-search around it, push away from the rejects
- [ ] Word nudges: a mapping table for the terms that name real axes
      (brighter, darker, more wobble, shorter, dirtier, wider, thinner) editing
      the `.vital` JSON directly; vaguer phrasing moves the query vector instead
- [ ] Every accepted patch written out and openable in FL
- [ ] Undo, and a history of everything you've auditioned this session

**Exit criterion:** mouth noise to a patch you're happy with, loaded in FL, in
under two minutes, most of the time.

**Watch out:** audition latency is the whole experience. If picking between
candidates has any lag, the loop stops feeling like thinking and starts
feeling like waiting. Pre-render candidates; never render on click.

---

## Phase 3 — Personalisation  ·  3–5 sessions

The compounding advantage. It only has to understand one mouth.

- [ ] Log every accepted pick as a training pair — this should already have
      been happening since Phase 2
- [ ] Fine-tune the query encoder on VocalSketch's synthesizer classes, then
      on your own accumulated pairs
- [ ] Guard against overfitting to a handful of sessions; keep the general
      model as a fallback the user can switch back to

**Exit criterion:** measurable Recall@5 improvement over the Phase 1 baseline,
on imitations recorded on a **different day** from the training pairs. Same-day
held-out data will flatter it badly — voice, mic position and room all drift.

---

## Phase 4 — Notes from the same take  ·  4–5 sessions

- [ ] Split the recording into the timbre path and the pitch/rhythm path
- [ ] Onsets, pitch contour, energy envelope → a pattern
- [ ] Tuned deliberately forgiving: hard grid snap, hard scale snap, few
      confident notes over many uncertain ones
- [ ] Export `.mid` alongside the patch; later, loopMIDI and FL's piano-roll
      scripting for direct delivery

**Exit criterion:** one "bwaaow bwaow bwaow" produces a patch *and* a pattern
that plays it, and the pattern needs under ~10 edits to be usable.

**Sequenced late on purpose.** It's the least novel part, the part that's
easiest to work around by hand, and it's the old plan's problem in a smaller,
more forgiving form. The sound is the product.

---

## Phase 5 — Breadth and release  ·  5–7 sessions

- [ ] Grow the corpus; make importing your own preset folders a one-click thing
- [ ] Consider a second synth. Serum is the obvious candidate and the honest
      compromise: hosted via DawDreamer, parameters nudgeable, presets not
      authorable — a strictly weaker experience than Vital, worth it only if
      the Serum library is where your sounds actually are
- [ ] Installer, first-run setup, error reporting
- [ ] Decide the shape: personal tool, free release, open source, or paid

**Exit criterion:** a v1.0 installer someone else can use end to end.

---

## Piano mode track  ·  independently schedulable

A second, separate mode restored per [D6](decisions.md#d6--piano-mode-is-back-in).
Not a feature of the sound-design flow above — no vocal query, no Vital
preset, no retrieval — so it does not depend on Phases 1–3 and can be
scheduled in any order relative to them.

- [ ] Resolve the open question in D6: is the target a MIDI controller/
      keyboard, or an acoustic piano with separate MIDI capture? The
      mechanism differs significantly depending on the answer
- [ ] AI suggests a concrete candidate MIDI sequence (not a scale/key
      constraint) for the captain to play
- [ ] That sequence takes over what the piano's keys produce
- [ ] Manipulation of the live sequence: timing, note density, note length
- [ ] Something demonstrable end to end, on whichever hardware D6 resolves to

**Exit criterion:** the captain plays a suggested sequence live on his piano
and reshapes it — timing, density, note length — in real time.

**Not yet scoped:** session count. D6's open question needs an answer first;
estimating before that is guessing at the wrong problem.

---

## Definition of done for v1.0

A Windows app where you make a noise, pick from five patches, say "brighter,
shorter", and end up with a Vital preset and a MIDI pattern in FL Studio.
Offline. No account.

## Later, explicitly not now

- **Solving parameters from scratch** (the Genopatch approach). Raises the
  ceiling past what the preset library contains. Revisit once retrieval and
  the refinement loop are good, because it needs both as scaffolding.
- **Drums and samples.** Vocal percussion → drum sample selection is the same
  retrieval architecture pointed at a sample library, and a natural Phase 6.
- **Real-time / live use.** Nothing here needs it.
- **Timbre transfer** (neural vocal → target sound). Rejected on purpose: it
  produces audio, not a patch, so you can't keep editing it. That defeats
  the point.

## Risk register

| Risk | Severity | Mitigation |
| --- | --- | --- |
| The cross-modal gap — your voice and a synth are just too different | High | The core bet. Attacked in order: domain normalisation, CLAP, VocalSketch fine-tuning, personalisation. Phase 1 exists to find out early, cheaply, with a number |
| Retrieval ceiling — the sound isn't in the library | High | Nudging covers small gaps; a bigger corpus covers more; parameter solving is the eventual answer. Be honest in the UI when nothing scores well |
| DawDreamer can't host Vital reliably | High | Phase 0, day one. Fallbacks: Vital's own CLI if any, or Surge XT, which ships Python bindings |
| Audition latency kills the loop | Medium | Pre-render candidates, never render on click. Treat it as a hard requirement, not an optimisation |
| Synplant 2 already does sample → patch | Medium | Different input (vocal imitation, not a real recording), different target (real third-party synths, not one built-in engine), and it has no iterative "no, more like this" loop |
| Vocalising a sound is a skill you may not have | Medium | Picking from candidates works without it. Personalisation adapts to however you actually make noises rather than requiring you to be good at it |
| Preset licensing for redistribution | Low | Only matters if you ship a bundled corpus. Index the user's own preset folders instead, and the question mostly evaporates |
| Scope creep back into transcription | Low | The sound is the product. Notes are Phase 4 and deliberately crude |

## Start here

Phase 0, this week. Two questions, one afternoon: *can a script drive Vital,
and is the preset really just JSON?* Answer those and the whole plan is either
confirmed or usefully wrong.
