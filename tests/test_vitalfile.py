import gzip
import json

import pytest

from voxfl.vitalfile import Preset, VitalFileError, diff

FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"


@pytest.fixture
def basic():
    return Preset.load(FIXTURES / "basic.vital")


def test_loads_and_reads_metadata(basic):
    assert basic.name == "Test Bass"
    assert basic.meta()["preset_style"] == "Bass"
    assert basic.was_gzipped is False


def test_params_are_only_numeric_settings(basic):
    params = basic.params()
    assert params["filter_1_cutoff"] == 64.0
    assert "lfos" not in params          # nested structure, not a knob
    assert "preset_name" not in params   # top level, not a setting


def test_flatten_summarises_bulk_arrays(basic):
    flat = basic.flatten()
    wave = "settings.wavetables.0.groups.0.wave_data[]"
    assert "omitted" in str(flat[wave])
    assert flat["settings.lfos.0.name"] == "Triangle"

    full = basic.flatten(include_bulk=True)
    assert "settings.wavetables.0.groups.0.wave_data.0" in full
    assert len(full) > len(flat)


def test_get_set_nudge_round_trip(basic, tmp_path):
    assert basic.get("settings.filter_1_cutoff") == 64.0

    before = basic.set("settings.filter_1_cutoff", 90.0)
    assert before == 64.0
    assert basic.get("settings.filter_1_cutoff") == 90.0

    was, now = basic.nudge("settings.filter_1_cutoff", -12.0)
    assert (was, now) == (90.0, 78.0)

    out = basic.save(tmp_path / "out.vital")
    assert Preset.load(out).get("settings.filter_1_cutoff") == 78.0


def test_set_rejects_unknown_path(basic):
    with pytest.raises(KeyError):
        basic.set("settings.no_such_knob", 1.0)


def test_nudge_rejects_non_numeric(basic):
    with pytest.raises(TypeError):
        basic.nudge("settings.lfos.0.name", 1.0)


def test_indexes_into_lists(basic):
    assert basic.get("settings.modulations.0.destination") == "filter_1_cutoff"
    basic.set("settings.modulations.0.destination", "osc_1_level")
    assert basic.get("settings.modulations.0.destination") == "osc_1_level"


def test_diff_finds_the_changed_knob():
    a = Preset.load(FIXTURES / "basic.vital")
    b = Preset.load(FIXTURES / "brighter.vital")
    result = diff(a, b)

    assert result
    assert result.changed["settings.filter_1_cutoff"] == (64.0, 88.0)
    assert result.changed["preset_name"] == ("Test Bass", "Test Bass Bright")
    assert not result.added and not result.removed


def test_diff_of_identical_presets_is_empty():
    a = Preset.load(FIXTURES / "basic.vital")
    b = Preset.load(FIXTURES / "basic.vital")
    assert not diff(a, b)


def test_gzip_round_trip(tmp_path, basic):
    packed = tmp_path / "packed.vital"
    packed.write_bytes(gzip.compress(json.dumps(basic.data).encode()))

    loaded = Preset.load(packed)
    assert loaded.was_gzipped is True
    assert loaded.name == "Test Bass"

    out = loaded.save(tmp_path / "again.vital")   # stays gzipped by default
    assert out.read_bytes()[:2] == b"\x1f\x8b"
    assert Preset.load(out).name == "Test Bass"


def test_rejects_non_json(tmp_path):
    bad = tmp_path / "bad.vital"
    bad.write_text("this is not json")
    with pytest.raises(VitalFileError, match="not valid JSON"):
        Preset.load(bad)


def test_rejects_binary(tmp_path):
    bad = tmp_path / "bad.vital"
    bad.write_bytes(b"\x00\x01\x02\xff\xfe")
    with pytest.raises(VitalFileError):
        Preset.load(bad)
