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
- Output lands at `plugin/builds/linux_vst/build/Vital.vst3/Contents/<arch>-linux/Vital.so`
  inside a real `.vst3` bundle directory — point `voxfl.render.VitalHost`/`--plugin` at the
  bundle directory, not the inner `.so`.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
