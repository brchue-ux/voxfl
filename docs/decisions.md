# Decision log

---

## D0 — This is a sound-design tool, not a transcription tool

**Decided.** The first version of this plan assumed the job was getting your
voice into FL as notes. That was wrong, and the correction reshapes everything.

The real problem: you know what the sound in your head is, but you don't know
which plugin makes it, which preset to start from, or which of two hundred
knobs to turn. The learning curve of *finding and tuning a sound* is the
bottleneck — not note entry.

So your mouth noise is a **description of a timbre**, not audio to be
transcribed. Nothing about your voice ends up in the track.

**Everything downstream of this changed:** the target (a synth patch, not a
MIDI file), the core technical risk (cross-modal retrieval, not pitch
tracking), and the competitive landscape (Dubler and DubBox solve
transcription, which is not this problem, so they stop being relevant).

---

## D1 — Target Vital first

**Decided.** Vital's presets are plain JSON text.

This is not a small convenience — it decides how much control the program has:

| Synth | What a program can do with a preset |
| --- | --- |
| **Vital** | Read every parameter by name, change it, and write a complete new patch as text |
| Serum | Set exposed plugin parameters and save opaque state — but not read what a preset *means*, or author one. Also paid |
| FL stock (Sytrus, Harmor) | Proprietary formats, and much smaller community preset libraries to search |
| Surge XT | Fully open with official Python bindings — the easiest to automate, but the smallest EDM preset ecosystem |

Vital is also free, which matters twice over: no purchase to start, and a
large body of freely available presets to index.

**Known limitation:** Vital is not the industry default the way Serum is, so
"the exact sound off that record" is less likely to be sitting in its library.
If it turns out your sounds live in a Serum collection you already own,
Phase 5 reconsiders — accepting the weaker, parameters-only experience.

**Reverses if:** DawDreamer can't host Vital reliably. Fallback is Surge XT,
which is the easiest of all to drive from Python.

---

## D2 — Retrieve, then nudge

**Decided.** Find the nearest existing preset, then adjust its parameters —
rather than solving synth parameters from scratch against your target.

**Why:** it always returns a real patch built by a human who knew what they
were doing, it's instant rather than an optimisation loop, and it degrades
gracefully — a mediocre result still hands you five real starting points,
which already beats scrolling a preset browser blind.

**Cost, stated plainly:** retrieval can only find what the library contains.
Nothing in the corpus close to what you meant means no result close to what
you meant. Nudging covers small gaps. Parameter solving is what raises that
ceiling, and it's deliberately parked as post-v1 rather than dropped.

---

## D3 — Words and candidate-picking for refinement

**Decided.** Two ways to say "nope, more like this":

- **Words** for the axes that have names — brighter, more wobble, shorter,
  dirtier. These map to real parameters and edit the JSON directly, so they're
  predictable and reversible.
- **Picking from five candidates** for everything else. Simpler than it
  sounds, faster than it sounds, and it doubles as the source of
  personalisation training data.

Vocal re-imitation ("no, more like *this*" as another noise) was considered
and deferred. It matches how you think, but interpreting a second noise as a
*direction to move in* rather than a fresh query is substantially harder, and
picking from candidates gets to the same place with far less machinery.

---

## D4 — Notes come from the same take, but late

**Decided.** The same recording yields both the timbre query and a pitch/
rhythm pattern — one take, two outputs.

Scheduled as Phase 4 because it's the least novel part of the system, the
easiest to work around by hand, and much more forgiving here than in a
transcription tool: you're expressing rough contour and rhythm, so snapping
hard to grid and scale is correct rather than lossy.

---

## D5 — Personalisation is the compounding advantage

**Decided.** Every accepted candidate is a labelled pair — *this noise* meant
*that patch*. They accumulate from ordinary use at zero extra effort.

The system never has to understand vocal imitation in general. It has to
understand one person's mouth, which is a dramatically easier problem, and it
gets better at it every session. Public datasets get it off the ground;
personal data is what makes it good.

---

## Prior art

The relevant landscape is completely different from the transcription one, and
the competitors from that plan (Dubler 2, DubBox, imitone) are no longer
competitors at all.

| Product / work | What it does | Overlap |
| --- | --- | --- |
| [Synplant 2 — Genopatch](https://soniccharge.com/synplant) | Give it an audio sample, its AI reverse-engineers synth settings that match. Also **PhenoType**, which generates patches from text prompts | Closest prior art by far |
| Sononym | Sample browser with timbral similarity search | Same retrieval idea, pointed at samples rather than presets |
| Splice / Ableton "similar sounds" | Find samples that sound like this one | Sample search, not patch selection |
| [VocalSketch](https://github.com/interactiveaudiolab/VocalSketchDataSet) / [Vocal Imitation Set](https://github.com/interactiveaudiolab/VocalImitationSet) | Research datasets of vocal imitations, including synthesizer sounds | Training data, not a competitor |
| [CLAP](https://github.com/LAION-AI/CLAP) | Shared audio + text embedding space | A component — probably the most important one |
| [DawDreamer](https://github.com/DBraun/DawDreamer) | Host and render VST plugins from Python | The tool the corpus build depends on |

**Where the gap is.** Synplant takes a *real recording* of the sound you want
— which assumes you already have one. The entire premise here is that you
don't; all you have is a noise you can make with your mouth. It also targets
only its own built-in engine, and offers no iterative "no, more like this"
conversation.

Nothing found does: **vocal imitation → a patch in a real third-party synth →
conversational refinement → a preset file you keep.** That's a genuine gap,
and it's a more defensible one than the transcription plan had.

**The catch:** it is genuine partly because it's hard. Synplant sidesteps the
cross-modal gap entirely by demanding real audio. Taking a vocal query instead
is the harder problem, and Phase 1 exists to find out early whether it's
tractable.
