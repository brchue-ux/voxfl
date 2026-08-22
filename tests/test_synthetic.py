import numpy as np

from voxfl.corpus import build_manifest
from voxfl.synthetic import (
    ROLES,
    build_synthetic_benchmark,
    build_synthetic_corpus,
    imitation_params,
    sample_params,
    synth_tone,
)


def test_build_synthetic_corpus_writes_a_manifest_buildable_tree(tmp_path):
    presets, short_dir, long_dir = build_synthetic_corpus(tmp_path, per_role=2, seed=0)
    assert len(presets) == len(ROLES) * 2

    items = build_manifest(short_dir, long_dir)
    assert len(items) == len(presets)
    for item in items:
        assert item.role in ROLES
        assert item.short_wav and item.long_wav


def test_build_synthetic_benchmark_writes_one_recording_per_preset(tmp_path):
    presets, _, _ = build_synthetic_corpus(tmp_path, per_role=2, seed=0)
    recordings = build_synthetic_benchmark(presets, tmp_path, seed=1)
    for preset in presets:
        assert (recordings / f"{preset.id}.wav").is_file()


def test_imitation_correlates_brightness_with_the_target_more_than_chance():
    rng = np.random.default_rng(0)
    diffs_correlated, diffs_random = [], []
    for _ in range(50):
        target = sample_params("lead", rng)
        imit = imitation_params(target, rng)
        diffs_correlated.append(abs(imit.brightness - target.brightness))

        other = sample_params("lead", rng)
        diffs_random.append(abs(imit.brightness - other.brightness))

    # The imitation's brightness should track its own target's brightness
    # noticeably more closely than an unrelated target's — this is the one
    # property the whole synthetic benchmark depends on to be meaningful.
    assert np.mean(diffs_correlated) < np.mean(diffs_random)


def test_synth_tone_is_silent_only_at_zero_duration():
    rng = np.random.default_rng(0)
    params = sample_params("bass", rng)
    audio = synth_tone(params, duration=0.2, rng=rng)
    assert audio.size > 0
    assert np.max(np.abs(audio)) > 0.0
