# Evaluation

Without measurement, tuning this pipeline is superstition. Every change will
feel like an improvement on the take you happened to test it with.

## The reference set

30–50 recordings of **your own** humming, since you are the primary user and
your voice is the actual distribution.

Deliberately include the awkward cases:

- slow and fast tempos (60–160 BPM)
- low, comfortable, and strained register
- clean, sloppy, and deliberately out-of-tune takes
- scoops into notes, vibrato, glissando between notes
- audible breaths between phrases
- long sustained notes and fast runs
- background noise: fan, room tone, keyboard clicks

Each take gets hand-corrected ground-truth MIDI — open it in FL, fix it until
it is what you *meant*, export. This is slow and boring and it is the highest
leverage work in the project. Everything after it is measurable; without it,
nothing is.

Store takes as `.wav` + `.mid` pairs with a small JSON of tempo, key, and
notes on what makes each one hard. Keep the audio out of git (see
`.gitignore`) — a separate local folder or a release asset.

## Metrics

| Metric | Definition | Why |
| --- | --- | --- |
| **Onset F1** | Predicted note starts within ±50 ms of ground truth | Rhythm correctness. The one users notice first |
| **Pitch accuracy** | Of matched notes, fraction with the correct MIDI number | Melody correctness |
| **Octave-tolerant pitch accuracy** | Same, ignoring octave errors | Separates "wrong note" from "right note, wrong octave" — very different bugs with very different fixes |
| **Note-count delta** | Predicted count − ground-truth count | Catches the two failure modes sliders can fix: fragmentation (vibrato split into many notes) and merging |
| **Edit distance** | Insert/delete/modify operations to reach ground truth | The closest proxy for "how annoying is this to fix" |

Report all of them. A single score hides which failure mode moved.

## The harness

Because analysis is cached and interpretation is cheap
([architecture.md](architecture.md#the-one-idea-that-shapes-everything)):

1. Analyse the whole reference set once, cache to disk.
2. Sweep interpretation parameters — hundreds of configurations in seconds.
3. Print a leaderboard, and a per-take breakdown so regressions are traceable
   to specific recordings rather than an average.

Rules that keep this honest:

- **Fix a baseline first.** Run Basic Pitch end-to-end and record its numbers
  before writing any custom pipeline. If the custom path never beats it, that
  is a finding, not a failure — use it and spend the time on the UI.
- **Hold out a test split.** Tune on 70 %, report on 30 %. Otherwise you are
  fitting parameters to 40 specific recordings.
- **Every bug becomes a take.** A conversion that goes wrong in real use gets
  added to the reference set. The set should grow for the life of the project.
- **Also listen.** The metrics are proxies. Render the output and play it —
  some errors score well and sound awful, and the reverse.

## For Phase 3 (drums)

Same structure, different metrics: onset F1 stays, pitch accuracy is replaced
by **classification accuracy** and a per-class confusion matrix. Expect
closed-hat/open-hat and snare/clap to be the confusions worth tracking.

Critically, evaluate personalisation properly: hold out beatboxing recorded on
a *different day* from the training examples. Same-session held-out data will
flatter the model badly — voice, mic position, and room all drift.
