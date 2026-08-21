"""End-to-end verification of the 'state' route against a *real* hosted Vital.

Unlike test_vst3_state.py (pure byte-format tests, always run), this needs an
actual Vital.vst3/.dll and dawdreamer, so it's skipped unless both are
available. Point it at any Vital build - the from-source Linux build used to
verify this fix, or the captain's own licensed install on Windows:

    VOXFL_VITAL_PLUGIN="C:\\Program Files\\Common Files\\VST3\\Vital.vst3" \\
        pytest tests/test_state_route_live.py -v

It proves the fix does what the report set out to check: the state route
recovers real preset JSON from a live plugin, injecting a preset through it
audibly differs from both the default patch and the same preset applied
through the lossy 'params' route (which can't carry wavetables/LFO shapes).

Known gap on the from-source Linux build used to develop this fix: this test
calls VitalHost.apply_params(), which calls DawDreamer's
get_parameters_description() - a bulk parameter-metadata fetch that
segfaults inside Vital's own ValueBridge::getText on that specific
self-built binary only (see AGENTS.md). Every other step (state dump/
decode/inject/render, and apply_params() itself called one parameter at a
time as a workaround) ran clean. Not expected to reproduce against a real
Vital install, where get_parameters_description() already works (it's how
the report's own probe measured 'params' route coverage).
"""

from __future__ import annotations

import copy
import os

import pytest

pytest.importorskip("dawdreamer")

PLUGIN_PATH = os.environ.get("VOXFL_VITAL_PLUGIN")
pytestmark = pytest.mark.skipif(
    not PLUGIN_PATH,
    reason="set VOXFL_VITAL_PLUGIN to a real Vital.vst3/.dll to run this against a live plugin",
)


def _mutate_preset_json(data: dict) -> dict:
    """A preset that differs *unmistakably* from ``data``, without assuming
    an exact schema.

    Two mistakes an earlier version of this function made, found by actually
    listening to the render rather than trusting peak/rms alone (see the PR
    that added this comment):

    - A plain polarity flip (``-1 * x``) on wavetable/LFO sample arrays is
      inaudible - human hearing doesn't perceive absolute phase - so it
      didn't prove the data was really reaching the engine. This clips/
      distorts the shape instead, which actually changes harmonic content.
    - Changing a filter's cutoff/resonance is a no-op if the filter itself
      is bypassed (``filter_1_on``/``filter_2_on`` were 0.0 in the real
      default patch this was developed against) - so every filter the
      patch has gets switched on here too, not just retuned. The cutoff
      drop is deliberately modest (-10, not the captain's own "-80" test):
      cutoff is in "note" units roughly aligned with MIDI pitch, and an
      80-unit drop undercuts render_note()'s default note (48) entirely,
      collapsing the sustained tone to near-silence rather than muffling
      it - dramatic in a way that looks like a bug, not a preset change.
    """
    mutated = copy.deepcopy(data)
    settings = mutated.get("settings", mutated)

    for key in list(settings) if isinstance(settings, dict) else []:
        if key.endswith("_on") and f"{key[:-3]}_cutoff" in settings:
            base = key[:-3]
            settings[key] = 1.0
            settings[f"{base}_cutoff"] = max(0.0, float(settings[f"{base}_cutoff"]) - 10.0)
            if f"{base}_resonance" in settings:
                settings[f"{base}_resonance"] = min(1.0, float(settings[f"{base}_resonance"]) + 0.3)

    def walk(node):
        if isinstance(node, list):
            is_float_array = node and all(
                isinstance(x, (int, float)) and not isinstance(x, bool) for x in node
            )
            if is_float_array and len(node) > 32:
                for i, x in enumerate(node):
                    node[i] = max(-1.0, min(1.0, float(x) * 6.0))
            else:
                for item in node:
                    if isinstance(item, (dict, list)):
                        walk(item)
        elif isinstance(node, dict):
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)

    walk(settings)
    mutated["preset_name"] = f"{mutated.get('preset_name', 'preset')} (voxfl state-route check)"
    return mutated


def _audio_close(a, b, atol: float = 1e-3) -> bool:
    import numpy as np

    a, b = np.asarray(a), np.asarray(b)
    n = min(a.shape[-1], b.shape[-1])
    return bool(np.allclose(a[..., :n], b[..., :n], atol=atol))


def test_state_route_carries_full_fidelity_and_differs_from_params(tmp_path):
    from voxfl.render import VitalHost, audio_summary, write_wav
    from voxfl.vitalfile import Preset

    host = VitalHost(PLUGIN_PATH)

    # 1. dump + decode the default patch's state (the report's own next step)
    default_blob = host.dump_state(tmp_path / "default_state.bin")
    assert default_blob.holds_vital_json, "parse_state() did not recover the default patch's JSON"
    assert {"settings", "synth_version", "preset_name"} <= set(default_blob.payload)

    default_audio = host.render_note()
    write_wav(tmp_path / "default.wav", default_audio)

    # 2. a preset that differs meaningfully from the default patch
    mutated = _mutate_preset_json(default_blob.payload)
    preset = Preset(data=mutated)

    # 3. inject and render via the 'state' route
    injected = default_blob.rebuild_with(preset)
    state_path = tmp_path / "injected_state.bin"
    state_path.write_bytes(injected)
    host.apply_state_file(state_path)
    state_audio = host.render_note()
    write_wav(tmp_path / "state_route.wav", state_audio)

    # 4. the SAME preset via 'params', on a fresh instance so nothing compounds
    params_host = VitalHost(PLUGIN_PATH)
    params_host.apply_params(preset)
    params_audio = params_host.render_note()
    write_wav(tmp_path / "params_route.wav", params_audio)

    state_summary = audio_summary(state_audio)
    assert state_summary["peak"] > 1e-5, "state-route render was silent - the preset probably didn't apply"

    assert not _audio_close(state_audio, params_audio), (
        "state-route and params-route renders were indistinguishable "
        f"(state={state_summary}, params={audio_summary(params_audio)}) - "
        "wavetable/LFO data doesn't appear to be taking effect"
    )
    assert not _audio_close(state_audio, default_audio), (
        "state-route render was indistinguishable from the default patch "
        f"(state={state_summary}, default={audio_summary(default_audio)})"
    )
