# Phase 0 runbook

Two questions, one afternoon:

1. **Can a script drive Vital?** — load it headlessly, apply a preset, render audio.
2. **Is a `.vital` preset really just JSON?** — read it, change it, write it back,
   and have Vital open the result.

Answer both and the architecture is confirmed. Fail either and the plan changes
now rather than in week six.

Everything here runs from a terminal. This is the only phase that does —
[Phase 2](ROADMAP.md#phase-2--the-loop-that-makes-it-usable) is the real UI.

## Setup

```bash
pip install -r requirements.txt
export PYTHONPATH=src        # Windows: set PYTHONPATH=src
```

You'll also need [Vital](https://vital.audio) installed (the free tier is
fine) and a folder of presets. Vital's own factory presets work to start.

## Question 2 first — the preset format

Cheaper, and it needs no plugin hosting. Start here.

```bash
python -m voxfl.preset inspect "C:\path\to\some.vital"
```

Prints every scalar in the file as a dotted path. Narrow it down:

```bash
python -m voxfl.preset inspect some.vital --match cutoff
python -m voxfl.preset inspect some.vital --match env_1
```

**The round trip** — change a value, write a new preset, open it in Vital:

```bash
python -m voxfl.preset nudge some.vital settings.filter_1_cutoff +24 -o brighter.vital
```

Load `brighter.vital` in Vital. If it opens and sounds brighter, question 2 is
answered and the whole "author patches as text" premise holds.

### The trick worth knowing

`diff` is how you learn Vital's parameter names without documentation:

1. Open a preset in Vital.
2. Turn **one** knob.
3. Save under a new name.
4. Diff the two files.

```bash
python -m voxfl.preset diff before.vital after.vital
```

The parameter that knob writes to falls straight out. Do this for the dozen
knobs that matter — cutoff, resonance, attack, release, LFO rate, LFO depth,
drive, unison — and you have the mapping table that
[Phase 2's word nudges](architecture.md#3-refinement) are built on.

## Question 1 — driving Vital

```bash
python -m voxfl.vital probe -o phase0_out --preset some.vital
```

`probe` reports on three things in order:

- **Does it render at all?** Loads Vital, plays one note, measures the output.
  A non-zero peak means the hosting path works.
- **Is the plugin state the preset JSON?** This is the important one — see below.
- **How much would parameter-matching cover?** Only with `--preset`.

### The open question: how a preset reaches the plugin

DawDreamer can load `.fxp` and `.vstpreset` files. Vital uses neither. So
there are three candidate routes, and `probe` exists to find out which are
actually available:

| Route | How | Fidelity |
| --- | --- | --- |
| `state` | Vital's plugin state is *probably* the preset JSON itself. If so, a state file can be rebuilt around any preset's JSON | Complete — wavetables, modulations, everything |
| `params` | Match preset JSON keys to host parameter names, set them one at a time | **Lossy.** Wavetables, modulation routings and LFO shapes are not host parameters |
| `none` | Render whatever patch loaded by default | Proves rendering works, nothing more |

`state` is a hypothesis, not a fact — it rests on Vital's `getStateInformation`
returning its JSON, which is likely but unverified. `probe` tests it directly
and tells you which route to use.

If `state` works, use it. If it doesn't, `params` still gets a corpus built,
but every rendering will be missing its wavetable — which matters enormously
for timbre, so that outcome is worth knowing before Phase 1 embeds anything.

### Render a preset

```bash
python -m voxfl.vital render some.vital --route state -o phase0_out
```

Silence is the failure mode to watch for: it usually means the preset didn't
apply, not that the preset is quiet. The tool warns and exits non-zero.

### Time a real corpus build

```bash
python -m voxfl.vital batch "C:\presets" --limit 100 -o phase0_out
```

Renders 100 presets, mirrors the source folder structure into the output —
**which is how preset-pack folder names survive as free role labels**
(`Bass/`, `Lead/`, `Pad/`) for Phase 1's role filtering — and extrapolates how
long 5,000 would take.

## Exit criteria

- [ ] `inspect` prints readable parameters from a real `.vital` file
- [ ] `nudge` produces a file Vital opens, and it sounds different
- [ ] `diff` reveals the parameter name behind a knob you turned
- [ ] `probe` renders a non-silent note
- [ ] `probe` says which preset route is available
- [ ] `batch --limit 100` completes and gives a corpus-build estimate

## What's verified and what isn't

Verified here: the preset reader, writer, differ and nudger (22 tests, run
`python -m pytest tests/ -q`), and the DawDreamer render-to-wav chain against
a built-in oscillator.

**Not verified:** anything involving Vital itself. This was developed on Linux
with no Vital installed and no way to listen to the output. The `state` route
in particular is an untested hypothesis. Expect the first run to need
adjustment, and treat surprises as the point of the exercise rather than as
bugs.
