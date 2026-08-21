# voxfl

Make a mouth noise, get the synth patch you meant.

You know what the sound in your head is. You don't know which plugin makes it,
which preset to start from, or which of 200 knobs to turn. voxfl closes that
gap: you vocalise the sound, it finds a Vital patch that matches, and you push
it around with plain words and A/B choices until it's right.

The same take also gives you the notes and rhythm, so "bwaaow bwaow bwaow"
yields a patch *and* a pattern.

A second, independent mode: **piano mode**. The AI suggests a concrete MIDI
sequence to play, that sequence takes over your piano's keys, and you perform
and reshape it live — timing, note density, note length. See
[D6](docs/decisions.md#d6--piano-mode-is-back-in) and the
[roadmap track](docs/ROADMAP.md#piano-mode-track--independently-schedulable).

## Status

Phase 0 (prove the preset corpus loop) and Phase 1 (retrieval harness,
baselines, evaluation) are built. See [docs/phase1.md](docs/phase1.md) for
what's measured and what's still the captain's own step: recording the
personal benchmark and running it against the real preset corpus.

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

## Phase 0 + Phase 1 tools

Command-line only. They are experiments, not the product —
[Phase 2](docs/ROADMAP.md#phase-2--the-loop-that-makes-it-usable) is the
desktop app. See the [Phase 0](docs/phase0.md) and [Phase 1](docs/phase1.md)
runbooks for the full walkthroughs.

```bash
pip install -r requirements.txt
export PYTHONPATH=src

# Phase 0: read, edit and compare .vital presets
python -m voxfl.preset inspect some.vital --match cutoff
python -m voxfl.preset nudge some.vital settings.filter_1_cutoff +24 -o brighter.vital
python -m voxfl.preset diff before.vital after.vital

# Phase 0: drive Vital headlessly and render presets to audio
python -m voxfl.vital probe -o phase0_out --preset some.vital
python -m voxfl.vital batch "C:\presets" --limit 100 -o phase0_out

# Phase 1: build the corpus manifest + embeddings, the benchmark, and evaluate
python -m voxfl.corpus manifest corpus_wav/short corpus_wav/long -o corpus/manifest.jsonl
python -m voxfl.benchmark scaffold corpus/manifest.jsonl -o benchmark
python -m voxfl.benchmark ingest benchmark/manifest.jsonl benchmark/recordings
python -m voxfl.evaluate corpus/manifest.jsonl benchmark/manifest.jsonl -o report.json
```

Run the tests with `python -m pytest tests/ -q`.

## Docs

- [Phase 0 runbook](docs/phase0.md) — what to run first, and what it proves
- [Phase 1 runbook](docs/phase1.md) — the benchmark harness, corpus embedding, baselines and results
- [Roadmap](docs/ROADMAP.md) — six phases, exit criteria, risks
- [Architecture](docs/architecture.md) — the retrieval pipeline and why it's shaped this way
- [Decisions](docs/decisions.md) — decision log and what already exists
- [Evaluation](docs/evaluation.md) — how we measure "did it find the sound I meant"
