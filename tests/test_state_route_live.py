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
self-built binary only (see AGENTS.md). It ran clean against every other
step (state dump/decode/inject/render); see build/e2e_verify.py in the PR
that introduced this file for the same verification via a one-parameter-
at-a-time workaround. Not expected to reproduce against a real Vital
install, where get_parameters_description() already works (it's how the
report's own probe measured 'params' route coverage).
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
    """A preset that differs meaningfully from ``data``, without assuming an
    exact schema: flip every long float array (wavetable frames, LFO shapes -
    never reachable through the 'params' route) and nudge filter/level
    scalars (reachable through either route, so this alone wouldn't
    distinguish 'state' from 'params')."""
    mutated = copy.deepcopy(data)

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, (dict, list)):
                    walk(value)
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    lowered = key.lower()
                    if "cutoff" in lowered or "resonance" in lowered or "level" in lowered:
                        node[key] = min(1.0, max(0.0, float(value) * 0.3 + 0.5))
        elif isinstance(node, list):
            is_float_array = node and all(
                isinstance(x, (int, float)) and not isinstance(x, bool) for x in node
            )
            if is_float_array and len(node) > 32:
                for i, x in enumerate(node):
                    node[i] = -1.0 * float(x)
            else:
                for item in node:
                    if isinstance(item, (dict, list)):
                        walk(item)

    walk(mutated.get("settings", mutated))
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
