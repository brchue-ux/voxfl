# Decision log

Short entries. Each records what was decided, why, and what would change it.

---

## D1 — Target FL Studio on Windows

**Decided.** FL Studio is the DAW in use; Windows is the platform. This fixes
the MIDI plumbing (loopMIDI rather than macOS's built-in IAC Driver), the
audio API (WASAPI), and packaging (PyInstaller → installer).

**Reverses if:** the tool goes commercial, at which point macOS and generic
MIDI matter more than FL-specific depth.

---

## D2 — Take-based conversion, not real-time

**Decided.** You record a fixed number of bars, then it converts.

**Why:** accuracy and architecture, in that order.

1. A real-time system must decide what each note is before hearing what
   follows. A take-based one sees the whole phrase — it can infer key from all
   the notes, fix a pitch by its neighbours, and fit the grid globally. It is
   simply a better-informed problem.
2. It permits the analysis/interpretation split (see
   [architecture.md](architecture.md#the-one-idea-that-shapes-everything)),
   which is what makes the parameters instant and the tuning measurable.
3. It removes the latency requirement entirely — no ASIO, no buffer tuning, no
   real-time-safe code.

It also matches how loops actually get written: record four bars, fix them,
loop them.

**Cost:** it feels less magical than watching notes appear as you sing, and
that magic is what sells competitors. Accepted.

**Reverses if:** using it reveals that the break in flow between singing and
seeing the result is worse than the accuracy gain.

---

## D3 — Humming → melody before beatboxing → drums

**Decided.** Monophonic pitch tracking is the most solved problem in this
space, with strong open-source components available immediately. It proves the
entire pipeline — capture, analysis, interpretation, IR, FL output — end to
end, and everything the drum path needs is built along the way.

---

## D4 — Ship the `.mid` file route first

**Decided.** Exporting a MIDI file has zero technical risk, works on every FL
edition, and is genuinely how a lot of producers prefer to work. The fancier
routes (virtual MIDI port, FL piano-roll script) are enhancements layered on a
tool that already works.

---

## D5 — Python core, web UI

**Decided.** The hard part of this project is audio ML, and that ecosystem is
Python. The UI is a canvas piano roll, which the web platform does well. The
two talk over a local socket so the frontend shell stays swappable.

**Reverses if:** installer size or startup time becomes intolerable — the
fallback is moving inference to ONNX-in-JS and shrinking the Python side.

---

## D6 — The LLM edits patterns; it does not transcribe them

**Decided.** Transcription is signal processing. Feeding audio decisions to a
language model adds cost, latency, and confident wrongness. But *editing* a
pattern — "make the hats triplets", "harmonise a third above" — is genuinely a
language problem, and the JSON IR makes it a validated, previewable,
undoable operation.

This is also the honest answer to "where's the AI?": in the part where natural
language beats a menu, not sprinkled over the parts where DSP already wins.

---

## Positioning

The idea is not novel, and pretending otherwise would produce a bad plan.
What already exists:

| Product | What it does | Overlap |
| --- | --- | --- |
| [Dubler 2](https://vochlea.com/products/dubler2) (Vochlea) | Real-time voice → MIDI controller: sing, hum, whistle, beatbox | High — this is the commercial version of the voice mode |
| [DubBox](https://vochlea.com/products/dubbox) (Vochlea) | Beatbox → drum loops, **trained on your own vocal sounds**, up to 8 per project, exports MIDI | High — this is Phase 3, already shipped by someone else |
| [imitone](https://imitone.com/) | Voice → MIDI, real-time, pitch only | Medium |
| Waves OVox | Voice-driven MIDI plus harmonising and arp effects | Medium |
| [Basic Pitch](https://github.com/spotify/basic-pitch) (Spotify) | Free, Apache-2.0 audio → MIDI, offline | Component, not competitor — we use it |
| FL's own Newtone / Edison | Audio → score, built into FL (edition-dependent) | The real baseline, already on your machine |

Notably, DubBox's per-user vocal training is exactly the "personalise it to
your own mouth sounds" idea that looked like the differentiator. It is not one.

**What is actually left as a wedge:**

1. **FL-native workflow.** Every competitor is a generic standalone that
   speaks MIDI at your DAW from outside. A tool that places notes directly in
   the FL piano roll, maps to FPC, and knows your project tempo is a different
   experience. This is the strongest remaining gap.
2. **Plain-English pattern editing.** Dubler is an *instrument* — you play it
   and it obeys. Nothing in this list lets you say "double-time it and add a
   fill in bar 4" to a pattern you just sang. That is a real hole.
3. **Take-based accuracy.** Everything above is real-time, and therefore
   working with strictly less information than a take-based converter.
4. **It's yours.** Free, offline, no dongle, tuned on recordings of your own
   voice, shaped around how you actually work.

**The decision this forces, and it should be made early:** is voxfl a personal
tool or a product? As a personal tool it is clearly worth building — points 3
and 4 are enough, and the competitors' £150-and-a-USB-mic model is not
something you need. As a commercial product it needs points 1 and 2 to be
genuinely excellent, because it is entering a market with funded incumbents
and an established demo language.

Nothing in the roadmap changes for the first three phases either way. The
answer is needed by Phase 5.
