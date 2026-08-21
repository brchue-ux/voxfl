# Evaluation

The question this has to answer is unusually slippery: *did it find the sound
I meant?* There's no ground truth in a file somewhere. So we manufacture one.

## The personal benchmark

The trick is to run the task backwards. Instead of imagining a sound and
hoping the system finds it, start from a preset that already exists:

1. Pick ~50 presets across bass, lead, pad and pluck.
2. Listen to each one.
3. Record yourself imitating it.
4. Save the pair.

Now every query has a known correct answer, and retrieval becomes measurable.
This takes about half a day and it is the single highest-leverage thing in the
project — the equivalent of the old plan's hand-corrected MIDI, but far
cheaper to produce.

Include the awkward cases deliberately: sounds you find easy to imitate and
sounds you don't, sustained pads as well as short plucks, and a few where two
or three presets in the corpus are genuinely near-identical.

## Metrics

| Metric | Definition | Why |
| --- | --- | --- |
| **Recall@1** | The exact preset is the top hit | Strict, and honestly not the goal |
| **Recall@5** | It's in the five you're shown | The one that matters — five is what the UI displays |
| **Recall@20** | It's in the top twenty | Diagnostic: high R@20 with low R@5 means ranking is the problem, not embedding |
| **MRR** | Mean reciprocal rank | Single number for tracking regressions between runs |
| **Acceptable@5** | Of the five shown, would you *use* any? | Judged by ear, not automatable, and the truest measure |

That last one exists because the others share a flaw worth naming: a different
preset that sounds equally right counts as a *failure* under Recall. Retrieving
the exact source preset is a proxy for the real goal, not the real goal. Track
both — if Recall stays flat while Acceptable@5 climbs, the system is getting
better and the metric just can't see it.

Always report the whole set. A single score hides which part moved.

## Baselines, in order

Fix each before building the next, and keep the numbers:

1. **Random within role** — the floor. Surprisingly not terrible in a corpus of
   basses, which is exactly why it must be measured.
2. **Hand-crafted timbral features** with domain normalisation.
3. **CLAP embeddings**, no training.
4. **CLAP + role filtering.**
5. **Fine-tuned** on VocalSketch's synthesizer classes.
6. **Personalised** on your own accumulated pairs.

If a step doesn't beat the one before it, that's a finding worth having.
Skipping straight to step 6 would mean never knowing which parts earned their
complexity.

## Rules that keep it honest

- **Hold out by day, not by sample.** Personalisation evaluated on imitations
  from the same session as its training data will look far better than it is.
  Voice, mic position, and room all drift; a different-day split is the only
  meaningful test.
- **Every failure becomes a benchmark entry.** A search that goes wrong in real
  use gets recorded and labelled. The set should grow for the life of the
  project.
- **Also just listen.** Play the top five. Some failures score well and sound
  absurd, and some "misses" are better than the target.

## Measuring the refinement loop

Retrieval accuracy is only half the product. The loop is the other half, and it
has its own numbers:

| Metric | Why |
| --- | --- |
| **Rounds to acceptance** | How many picks and words before you're happy. The headline usability number |
| **Time to acceptance** | Wall clock, from recording to a patch in FL. Target under two minutes |
| **Nudge hit rate** | When you say "brighter", does the result read as brighter? Judged by ear, per word, and worth tracking per-term to find which mappings are wrong |
| **Audition latency** | Must be imperceptible. Any lag and the loop stops feeling like thinking |

Good retrieval with a slow loop loses to mediocre retrieval with a fast one.
The loop is where the product is won.

## For Phase 4 (notes)

The old melody metrics apply — onset F1 within ±50 ms, pitch accuracy,
octave-tolerant pitch accuracy, note-count delta — but with a lower bar. The
pattern is a rhythmic sketch you'll edit, not a transcription, so measure
whether the *rhythm* survives and treat pitch errors as much cheaper.
