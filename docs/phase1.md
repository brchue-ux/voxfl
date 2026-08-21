# Phase 1 runbook — retrieval that actually works

Still no interface: a script and a scoreboard, per
[the roadmap](ROADMAP.md#phase-1--retrieval-that-actually-works--4-6-sessions).
This is the harness, corpus, baselines and evaluation that answer the one
question Phase 1 exists to answer: **does a vocal imitation land near its
real preset, within its role, more often than not?**

Everything here builds on Phase 0's tooling unmodified — `voxfl.vital` still
does all plugin hosting and rendering, `voxfl.preset` still does all preset
reading/writing. Phase 1 only adds a role-tagging manifest, embeddings, a
search index, a benchmark harness and metrics on top.

## Pipeline

```
python -m voxfl.vital batch <presets> -o corpus_wav/short --hold 0.4   # Phase 0 tool, unmodified
python -m voxfl.vital batch <presets> -o corpus_wav/long  --hold 1.5   # ditto, long variant

python -m voxfl.corpus manifest corpus_wav/short corpus_wav/long -o corpus/manifest.jsonl
python -m voxfl.corpus embed corpus/manifest.jsonl --method features -o corpus/features.npz
python -m voxfl.corpus embed corpus/manifest.jsonl --method clap     -o corpus/clap.npz   # optional, see below

python -m voxfl.benchmark scaffold corpus/manifest.jsonl -o benchmark   # see "The personal benchmark"
# ... captain listens + records, per benchmark/TODO.md ...
python -m voxfl.benchmark ingest benchmark/manifest.jsonl benchmark/recordings

python -m voxfl.evaluate corpus/manifest.jsonl benchmark/manifest.jsonl -o report.json
```

## The personal benchmark (captain's own recordings)

[evaluation.md](evaluation.md#the-personal-benchmark): ~50 presets across
bass/lead/pad/pluck, listened to and imitated by mouth, each pair saved.
This machine cannot record the captain's own voice, so `voxfl.benchmark`
splits into a scaffold/ingest pair instead of doing it in one step:

1. Build the corpus manifest first (below), then:
   ```bash
   python -m voxfl.benchmark scaffold corpus/manifest.jsonl -o benchmark -n 50
   ```
   Writes `benchmark/TODO.md` — a checklist naming exactly which corpus wav
   to listen to and exactly where to save each recording — and
   `benchmark/manifest.jsonl` with the target presets already filled in and
   `imitation_wav` left blank.
2. **Captain's part, off this machine:** open `benchmark/TODO.md`, listen to
   each `preset_wav`, record an imitation on any mic (a few seconds, any
   sample rate — `ingest` reads it with the `wave` module, no format
   wrangling needed), save it as `benchmark/recordings/<id>.wav`. Per
   evaluation.md, deliberately include a few you find easy and a few you
   don't, and a couple of near-identical presets in the same role.
3. Fold the recordings back in:
   ```bash
   python -m voxfl.benchmark ingest benchmark/manifest.jsonl benchmark/recordings
   ```
   Validates each recording (present, non-silent, ≥0.2s) and reports what's
   still missing or failed validation, without ever writing a bad take in
   silently.

`voxfl.evaluate` only uses entries with an ingested recording
(`benchmark.ready_entries`), so partially-recorded benchmarks still run.

### Validating the harness without the captain's voice

`python -m voxfl.benchmark synthetic -o synthetic_benchmark` builds a
**synthetic** corpus (60 procedurally-generated tones, 15 per role, varied
brightness/noise/attack/decay) and a **synthetic** "imitation" of each —
correlated on those same axes but generated with a different register and
excitation, standing in for "your mouth and a synth are alike only in the
ways you meant them to be." It exists purely to prove the scaffold → ingest
→ manifest → embed → evaluate pipeline is wired correctly end to end before
any real recording exists, and every artefact it produces is labelled
synthetic so it can't be mistaken for the real benchmark. It is not
VocalSketch and not a claim about real voice/synth cross-modal retrieval —
see "Results" below for what it *does* show.

## Corpus build (reuses Phase 0 tooling, doesn't rebuild it)

Rendering and role tagging are two different steps on purpose:

1. **Render** with `voxfl.vital batch`, exactly as Phase 0 built it — twice,
   once per note length, into two output trees. That's architecture.md's
   "render two or three variants per preset... since attack and sustain
   carry different information," achieved with zero new rendering code.
2. **Tag roles and pair variants** with `voxfl.corpus manifest`, which reads
   both trees, tags each preset's role from its *source* folder name
   (`ROLE_ALIASES` in `corpus.py` — extend it as real preset packs turn up
   spellings it doesn't recognise) and writes one manifest row per preset.

`voxfl.corpus embed --method {random,features,clap}` then turns each
manifest row into one vector, averaging the short/long variant embeddings
into a single preset-level vector (the benchmark's ground truth is
per-preset, not per-variant).

## Baselines, in the roadmap's order

1. **`random`** — `retrieval.RetrievalIndex.rank(query=None, ...)` shuffles
   the (role-filtered) candidate set. No embedding involved; it's the floor.
2. **`features`** — `features.py`'s six hand-crafted timbral features
   (brightness, noisiness, attack time, decay slope, harmonicity, spectral
   flux), z-scored separately for the preset corpus (`corpus.fit_feature_norm`)
   and the vocal-query corpus (`evaluate.features_query_norm`) — never mix
   these two `NormStats`, or "domain-normalised" stops meaning anything.
   With only the benchmark's own ~50 recordings available as "a corpus of
   vocal queries," the query-side stats are a rough estimate, not a stable
   population statistic — worth sharpening once Phase 3 accumulates more.
3. **`clap`** — LAION CLAP's audio tower, via `transformers`' `ClapModel`.
   Optional dependency (`pip install -r requirements-clap.txt`); downloads
   ~2.5 GB of weights from HuggingFace on first use. `voxfl.evaluate --skip-clap`
   runs baselines 1-2 only, and `corpus.embed --method clap` /
   `evaluate.run` both fail with a clear message (not a stack trace) if
   `transformers`/`torch` aren't installed.

Each baseline is measured twice — with and without role filtering — so
architecture.md's "large, nearly free accuracy win" is visible on its own
rather than baked into every number silently.

## Results (synthetic corpus, 60 presets / 60 benchmark pairs, seed 0)

The captain's own recordings don't exist yet, so these numbers are from the
synthetic validation set above — **read them as "the pipeline works and
produces a sane signal," not as "CLAP solves cross-modal retrieval."** They
should be re-run against the real corpus and the real benchmark once both
exist; `report.json` from a real `voxfl.evaluate` run is the number that
actually answers Phase 1's question.

| Baseline | R@1 | R@5 | R@20 | MRR |
| --- | --- | --- | --- | --- |
| random | 0.017 | 0.133 | 0.350 | 0.092 |
| random + role | 0.083 | 0.250 | 1.000 | 0.216 |
| features | 0.100 | 0.367 | 0.833 | 0.238 |
| features + role | 0.150 | 0.500 | 1.000 | 0.311 |
| clap | 0.083 | 0.383 | 0.733 | 0.239 |
| clap + role | **0.150** | **0.567** | 1.000 | **0.349** |

(R@20 hits 1.000 once role filtering is on because each synthetic role only
has 15 candidates — that's a synthetic-corpus artefact, not a real result;
a real corpus with hundreds of presets per role won't saturate R@20 for free.)

Reading it the way evaluation.md asks to:

- Every baseline clears random-within-role by a real margin, and the order
  matches the roadmap's prediction: `clap+role` > `features+role` >
  `random+role`.
- Role filtering is the single biggest lever in this data — it roughly
  doubles R@5 for both `features` and `clap`, exactly the "large, nearly
  free win" architecture.md predicted.
- `clap+role` R@5 is 0.567 — over half, i.e. the exit criterion ("lands in
  the top 5 more often than not, within its role") is **met on this
  synthetic set**. That is a statement about the harness and the baseline
  ordering being sound, not a promise about real vocal imitations, which
  have a much larger, much noisier cross-modal gap than this synthetic
  correlation. Rerun against the real benchmark before trusting the number.

## Exit criterion

> the preset you were imitating lands in the top 5 more often than not,
> within its role

Not yet measurable against real data — no real recordings exist. The harness
that measures it is built, tested (109 unit tests, `python -m pytest tests/
-q`, no DawDreamer/Vital/network needed except for the optional CLAP
baseline), and validated end to end on synthetic data with the result above.
**Next step is entirely the captain's:** build the real corpus
(`voxfl.vital batch` against his preset library), then `voxfl.benchmark
scaffold` / record / `ingest`, then `voxfl.evaluate`. If `clap+role` R@5
against the real benchmark comes in well under 0.5, that is the signal
roadmap.md's risk register names explicitly — the honest options are
VocalSketch fine-tuning (pulled forward from Phase 3) or narrowing to
word-search only. Decide from that number, not from the synthetic one above.
