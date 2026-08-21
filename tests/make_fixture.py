"""Build a synthetic .vital-shaped preset.

This is NOT a real Vital preset — we have no way to verify Vital's exact
schema from here. It mimics the shape the tools have to survive: nested
settings, a bulky wavetable array, LFO objects and modulation routings.
The tools are schema-agnostic by design, so this exercises the real paths.
"""

import json
from pathlib import Path


def build(name="Test Bass", cutoff=64.0, release=0.35):
    return {
        "author": "voxfl fixture",
        "comments": "synthetic, for tests only",
        "preset_name": name,
        "preset_style": "Bass",
        "synth_version": "1.5.5",
        "settings": {
            "filter_1_cutoff": cutoff,
            "filter_1_resonance": 0.5,
            "filter_1_on": 1.0,
            "env_1_attack": 0.0,
            "env_1_release": release,
            "osc_1_level": 0.7,
            "osc_1_on": 1.0,
            "osc_2_level": 0.0,
            "volume": 0.75,
            "polyphony": 8.0,
            "lfos": [
                {"name": "Triangle", "num_points": 3,
                 "points": [0.0, 1.0, 0.5, 0.0, 1.0, 1.0]},
            ],
            "modulations": [
                {"source": "lfo_1", "destination": "filter_1_cutoff"},
                {"source": "", "destination": ""},
            ],
            "wavetables": [
                {"name": "Saw",
                 "groups": [{"wave_data": [i / 2048.0 for i in range(2048)]}]},
            ],
        },
    }


if __name__ == "__main__":
    here = Path(__file__).parent / "fixtures"
    here.mkdir(exist_ok=True)
    (here / "basic.vital").write_text(json.dumps(build()))
    (here / "brighter.vital").write_text(
        json.dumps(build(name="Test Bass Bright", cutoff=88.0, release=0.35))
    )
    print(f"wrote fixtures to {here}")
