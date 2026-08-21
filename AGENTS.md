# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## DawDreamer state dumps are wrapped, not bare JSON

A `.vital` preset is plain JSON, but what `synth.save_state()`/`load_state()` read and write is
**not** that JSON directly — it's JUCE's generic VST3 host-state format (`VC2!` magic + XML +
a nonstandard base64-encoded `<IComponent>` element) wrapping it. This is true of every JUCE
VST3 plugin, not a Vital quirk. See `src/voxfl/render.py`'s "JUCE VST3 wrapper" section
(`parse_state`, `juce_base64_encode`/`decode`) for the decode/encode implementation and its
primary-source citations, and `tests/test_vst3_state.py` for byte-format regression tests that
need no Vital/DawDreamer to run.

## Building Vital from source on Linux (no captain account/license needed)

`github.com/mtytel/vital` (GPLv3) builds with `make vst3 CONFIG=Release` from the repo root, but
two things aren't obvious:

- **Steinberg pulled the VST2 SDK from public distribution**, so the vendored
  `third_party/VST_SDK` has no `VST2_SDK/` dir. JUCE's VST3 wrapper still `#include`s a VST2
  header by default (`JUCE_VST3_CAN_REPLACE_VST2` defaults to 1) and fails with
  `pluginterfaces/vst2.x/vstfxstore.h: No such file or directory`. Fix: build with
  `CPPFLAGS="-DJUCE_VST3_CAN_REPLACE_VST2=0"` — it flows through the top-level Makefile's `vst3`
  target into the JUCE compile flags automatically.
- Needs standard JUCE 6 Linux build deps (alsa, freetype2, libcurl, X11 + extensions, GL,
  `libsecret-1`/`libglib2.0` for the bundled Firebase auth libs it statically links) — see
  `build/Dockerfile.vitalbuild` (gitignored scratch, not committed) for the exact package list.
  If sandboxed without passwordless sudo/apt, a `docker` group membership (check with
  `docker info`) is a viable no-sudo build sandbox — build system deps into an image, mount the
  cloned repo, run `make` inside the container, and the resulting `Vital.vst3` runs fine on the
  host (older container glibc is forward-compatible with a newer host).
- **A `CONFIG=Release` build (`NDEBUG` defined) compiles in real Firebase-auth calls that abort**
  (`ERROR: App ID and API key must be specified in App options.`) the first time anything touches
  auth — reproducibly, on any `setStateInformation`/preset load, not just a UI login. Root cause:
  `src/common/authentication.h` compiles the real Firebase-backed `Authentication` class whenever
  `NDEBUG && !NO_AUTH`, and `Authentication::create()` calls `firebase::App::Create()` with
  deliberately-empty app id/api key/project id. Build with `CPPFLAGS` also including `-DNO_AUTH=1`
  to get Vital's own no-op stub `Authentication` class instead — no Firebase project needed, no
  captain credentials involved.
- **This build (`JUCE_OPENGL3=1`, `juce_gui_basics`/`juce_opengl` compiled in) touches X11 even
  headlessly** — hosting it with DawDreamer needs a display (`xvfb-run -a ...`) even though no
  editor is ever created; without one it segfaults on plugin load.
- DawDreamer's `get_parameters_description()` (and thus `render.py`'s `VitalHost.parameters()`/
  `parameter_index()`/`apply_params()`) segfaults on this specific self-built binary inside
  Vital's own `ValueBridge::getText` (`JuceVST3EditController::Param::toString` ->
  `getParamStringByValue`) — reproducible, but only through that bulk-fetch call.
  `get_parameter_name(i)`/`get_parameter(i)`/`get_parameter_text(i)`/`set_parameter(i, v)` all
  work correctly called individually for every one of the 2852 parameters (matches the captain's
  own real-Vital parameter count exactly). Likely an old-ABI `std::string` quirk from
  `_GLIBCXX_USE_CXX11_ABI=0` (forced to link the prebuilt Firebase static libs) under a modern
  GCC 13 libstdc++, isolated to this one call — not reproduced against the captain's real Vital,
  and not a bug in this repo's code. `build/e2e_verify.py`'s `safe_apply_params` shows the
  one-at-a-time workaround if this needs revisiting.
- Output lands at `plugin/builds/linux_vst/build/Vial.vst3/Contents/<arch>-linux/Vial.so`
  inside a real `.vst3` bundle directory — point `voxfl.render.VitalHost`/`--plugin` at the
  bundle directory, not the inner `.so`. It's genuinely named `Vial`, not `Vital` — the
  README's "no use of the Vital/Tytel name or branding" restriction on from-source builds, not
  a typo.

## The 'params' route must not feed raw preset values into set_parameter()

`DawDreamer`'s `set_parameter`/`get_parameter` operate on VST3 host-automation values, which are
**always normalised to `[0, 1]`** — a hard VST3 spec fact, confirmed via `get_parameter_range()`.
Vital's own preset JSON (`Preset.params()`) stores many `settings` values in a real, per-parameter
unit instead: a real dumped default patch has `"volume": 5473.04`, `"filter_1_cutoff": 60.0` — not
fractions. `VitalHost.apply_params()` used to call `set_parameter(idx, float(raw_value))` directly;
for any value outside `[0, 1]` this silently clamps to 0 or 1 (e.g. that `volume` slams a host
fader to max), and if the clamped parameter has its own de-zip smoothing, the render captures a
multi-second linear ramp toward the wrong target followed by an abrupt cutoff at note-off — audible,
and easy to mistake for a rendering bug rather than a value-domain bug. Fixed by `_looks_normalised()`
gating `apply_params()`: skip (into `missed`) rather than guess when a value falls outside `[0, 1]`.
This can only rule out the *impossible* cases — a value that happens to land in `[0, 1]` (levels,
mix knobs, several already are) isn't proven correct, just not provably wrong.

## Vital's `filter_N_cutoff` is a "note" unit, and the default patch's filters are OFF

A real dumped default patch has `filter_1_on = filter_2_on = 0.0` — both filters bypassed — so
changing cutoff/resonance alone is inaudible; a demo preset needs to flip the matching `_on` flag
too. Cutoff itself is stored in a unit that tracks roughly with MIDI note number, not Hz or `[0,1]`:
`render_note()`'s default note is 48, and a cutoff at or below ~48 in that unit blocks the note's
own fundamental, collapsing a *held* note to near-silence rather than "muffled" (confirmed with a
cutoff-delta sweep — closing further than ~10-12 units below this patch's default of 60 drops
sustained energy off a cliff). A ~10-unit drop with the filter forced on and resonance boosted
lands just above the fundamental: dramatic and clearly audible without collapsing to silence.
Separately, a plain polarity flip on a wavetable/LFO sample array (`-1 * x`) is inaudible — hearing
doesn't perceive absolute phase — so proving injected wavetable/LFO data actually changes the sound
needs real waveshaping (e.g. gain-and-clip), not a sign flip.

## Phase 1 retrieval pipeline and its optional CLAP dependency

See `docs/phase1.md` for the full runbook. Two things not obvious from the
code:

- **CLAP's HF `transformers` API is a moving target.** `ClapProcessor.__call__`
  renamed its audio kwarg from `audios` to `audio` between versions, and
  `ClapModel.get_audio_features()`/`get_text_features()` return a plain
  `(batch, dim)` tensor on older `transformers` but a
  `BaseModelOutputWithPooling` (use `.pooler_output`) on newer ones —
  `embed.py`'s `ClapEmbedder.embed_file()` and `_extract_embedding()` handle
  both. If a future `transformers` upgrade breaks this again, the fix is
  narrow: adjust those two spots, not the retrieval pipeline around them.
- **Two `NormStats` must never be swapped.** `corpus.fit_feature_norm()` fits
  on the *preset* corpus; `evaluate.features_query_norm()` fits on the
  *vocal-query* corpus (currently just the benchmark's own recordings — a
  rough estimate until Phase 3 accumulates more). Passing the wrong one into
  `FeatureEmbedder` produces numbers that look fine and mean nothing —
  architecture.md's domain-normalisation point depends on keeping these
  separate.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
