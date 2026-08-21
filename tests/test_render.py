import json

import numpy as np
import pytest

from voxfl.render import _looks_normalised, audio_summary, parse_state, write_wav
from voxfl.vitalfile import Preset

FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"

PRESET_JSON = json.dumps({"preset_name": "X", "synth_version": "1.5.5",
                          "settings": {"volume": 0.5}}).encode()


@pytest.mark.parametrize("value", [0.0, 1.0, 0.5, 0.7071067811865476])
def test_looks_normalised_accepts_the_0_to_1_range(value):
    assert _looks_normalised(value)


@pytest.mark.parametrize(
    "value",
    [
        -0.001,
        1.001,
        60.0,  # a real dumped default patch's filter_1_cutoff (note units)
        5473.04052734375,  # the same patch's volume (raw gain, not a fraction)
    ],
)
def test_looks_normalised_rejects_values_outside_0_to_1(value):
    # apply_params() feeds preset.params() values straight into
    # set_parameter(), which — being VST3 host automation — is always
    # normalised to [0, 1]. Vital's own JSON stores many settings in a raw
    # per-parameter unit instead (note numbers, seconds, raw gain), so a
    # value outside [0, 1] cannot be a valid normalised parameter: feeding
    # it in would silently clamp to 0 or 1 rather than apply the real value.
    assert not _looks_normalised(value)


def test_parse_state_finds_bare_json():
    blob = parse_state(PRESET_JSON)
    assert blob.holds_vital_json
    assert blob.json_start == 0
    assert blob.prefix == b"" and blob.suffix == b""


def test_parse_state_finds_json_behind_a_binary_header():
    blob = parse_state(b"\x00\x01VST3" + PRESET_JSON)
    assert blob.holds_vital_json
    assert blob.prefix == b"\x00\x01VST3"


def test_parse_state_keeps_trailing_bytes():
    blob = parse_state(PRESET_JSON + b"\x00\x00tail")
    assert blob.holds_vital_json
    assert blob.suffix == b"\x00\x00tail"


def test_parse_state_reports_absence_rather_than_guessing():
    blob = parse_state(b"\x01\x02\x03 no json here")
    assert blob.payload is None
    assert blob.holds_vital_json is False


class _FakeSynth:
    """Just enough of DawDreamer's plugin-processor surface for apply_params()."""

    def __init__(self, param_names):
        self._names = param_names
        self.set_calls = []

    def get_parameters_description(self):
        return [{"name": name, "index": i} for i, name in enumerate(self._names)]

    def set_parameter(self, index, value):
        self.set_calls.append((index, value))
        return True


def test_apply_params_skips_raw_values_outside_normalised_range():
    from voxfl.render import VitalHost

    host = VitalHost.__new__(VitalHost)  # bypass __init__: no real plugin needed
    host.synth = _FakeSynth(["Volume", "Filter 1 Cutoff", "Osc 1 Level"])
    # modelled on a real dumped default patch: volume and filter_1_cutoff are
    # raw units (gain, note number), not normalised - only osc_1_level is.
    preset = Preset(data={
        "preset_name": "x", "synth_version": "1.5.5",
        "settings": {"volume": 5473.04052734375, "filter_1_cutoff": 60.0, "osc_1_level": 0.7071067690849304},
    })

    applied, missed = host.apply_params(preset)

    assert applied == 1
    assert set(missed) == {"volume", "filter_1_cutoff"}
    assert host.synth.set_calls == [(2, 0.7071067690849304)]  # only osc_1_level was ever set


def test_rebuild_preserves_prefix_and_suffix():
    blob = parse_state(b"HEAD" + PRESET_JSON + b"TAIL")
    preset = Preset.load(FIXTURES / "basic.vital")

    rebuilt = blob.rebuild_with(preset)
    assert rebuilt.startswith(b"HEAD")
    assert rebuilt.endswith(b"TAIL")

    inner = parse_state(rebuilt)
    assert inner.payload["preset_name"] == "Test Bass"


def test_rebuild_refuses_when_there_is_no_json():
    from voxfl.render import RenderError
    blob = parse_state(b"\x01\x02\x03")
    with pytest.raises(RenderError, match="no embedded JSON"):
        blob.rebuild_with(Preset.load(FIXTURES / "basic.vital"))


def test_write_wav_round_trips_stereo(tmp_path):
    import wave

    sr = 44100
    t = np.linspace(0, 0.25, int(sr * 0.25), endpoint=False)
    audio = np.stack([np.sin(2 * np.pi * 220 * t), np.sin(2 * np.pi * 330 * t)])

    out = write_wav(tmp_path / "t.wav", audio, sr)
    with wave.open(str(out)) as fh:
        assert fh.getnchannels() == 2
        assert fh.getframerate() == sr
        assert fh.getnframes() == audio.shape[1]


def test_write_wav_normalises_clipping_input(tmp_path):
    import wave

    loud = np.ones((1, 128)) * 4.0
    out = write_wav(tmp_path / "loud.wav", loud)
    with wave.open(str(out)) as fh:
        frames = np.frombuffer(fh.readframes(fh.getnframes()), dtype="<i2")
    assert frames.max() <= 32767          # normalised, not wrapped around
    assert frames.max() > 30000


def test_audio_summary_distinguishes_sound_from_silence():
    silent = audio_summary(np.zeros((2, 44100)))
    assert silent["peak"] == 0.0

    loud = audio_summary(np.ones((2, 44100)) * 0.5)
    assert loud["peak"] == 0.5
    assert loud["rms"] == pytest.approx(0.5)
    assert loud["seconds"] == pytest.approx(1.0)


def test_audio_summary_handles_empty():
    assert audio_summary(np.array([]))["peak"] == 0.0
