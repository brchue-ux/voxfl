# voxfl

Make a mouth noise, get the synth patch you meant.

You know what the sound in your head is. You don't know which plugin makes it,
which preset to start from, or which of 200 knobs to turn. voxfl closes that
gap: you vocalise the sound, it finds a Vital patch that matches, and you push
it around with plain words and A/B choices until it's right.

The same take also gives you the notes and rhythm, so "bwaaow bwaow bwaow"
yields a patch *and* a pattern.

## Status

Design locked, not yet built. Phase 0 (prove the preset corpus loop) is next.

## Decisions made

| Question | Answer |
| --- | --- |
| Target synth | Vital — presets are plain JSON, so patches can be read *and* authored |
| Target DAW | FL Studio on Windows |
| How it finds a sound | Retrieve the nearest preset, then nudge its parameters |
| How you correct it | Plain words ("brighter", "more wobble") and picking from candidates |
| Notes | Extracted from the same take as the timbre |

## What this is not

**Not a transcription tool.** It does not put your voice into the track
verbatim. Your mouth noise is a *description* of a sound, not the sound
itself — the whole job is translating that description into a real synth
patch you can keep editing.

Not a sample-based timbre transfer either: the output is a patch, so you stay
in control of it in FL afterwards.

## Docs

- [Roadmap](docs/ROADMAP.md) — six phases, exit criteria, risks
- [Architecture](docs/architecture.md) — the retrieval pipeline and why it's shaped this way
- [Decisions](docs/decisions.md) — decision log and what already exists
- [Evaluation](docs/evaluation.md) — how we measure "did it find the sound I meant"
