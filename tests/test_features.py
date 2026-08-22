import numpy as np
import pytest

from voxfl.features import FEATURE_NAMES, NormStats, load_mono, raw_features
from voxfl.render import write_wav

SR = 22050


def _tone(freq, n_harmonics, duration=0.5, sr=SR):
    t = np.arange(int(duration * sr)) / sr
    sig = np.zeros_like(t)
    for h in range(1, n_harmonics + 1):
        sig += np.sin(2 * np.pi * freq * h * t) / h
    return sig / np.abs(sig).max()


def test_raw_features_on_silence_is_all_zero():
    silence = np.zeros(SR)
    assert np.all(raw_features(silence, SR) == 0.0)


def test_brighter_tone_has_higher_centroid():
    dull = _tone(110, n_harmonics=1)
    bright = _tone(110, n_harmonics=16)
    dull_centroid = raw_features(dull, SR)[0]
    bright_centroid = raw_features(bright, SR)[0]
    assert bright_centroid > dull_centroid


def test_noise_has_higher_noisiness_than_a_pure_tone():
    rng = np.random.default_rng(0)
    tone = _tone(220, n_harmonics=4)
    noise = rng.normal(size=SR // 2)
    noise /= np.abs(noise).max()
    tone_noisiness = raw_features(tone, SR)[1]
    noise_noisiness = raw_features(noise, SR)[1]
    assert noise_noisiness > tone_noisiness


def test_slow_attack_has_longer_attack_time_than_fast_attack():
    t = np.arange(int(0.6 * SR)) / SR
    carrier = np.sin(2 * np.pi * 220 * t)
    fast = carrier * np.clip(t / 0.005, 0, 1)
    slow = carrier * np.clip(t / 0.3, 0, 1)
    fast_attack = raw_features(fast, SR)[2]
    slow_attack = raw_features(slow, SR)[2]
    assert slow_attack > fast_attack


def test_raw_features_returns_one_value_per_named_feature():
    tone = _tone(330, n_harmonics=6)
    assert raw_features(tone, SR).shape == (len(FEATURE_NAMES),)


def test_load_mono_round_trips_write_wav(tmp_path):
    tone = _tone(220, n_harmonics=4)
    path = write_wav(tmp_path / "tone.wav", tone[None, :], SR)
    mono, rate = load_mono(path)
    assert rate == SR
    assert mono.shape[0] == tone.shape[0]
    # 16-bit quantisation introduces a small but bounded error.
    assert np.max(np.abs(mono - tone)) < 1e-3


class TestNormStats:
    def test_fit_apply_gives_zero_mean_unit_variance(self):
        rng = np.random.default_rng(1)
        data = rng.normal(loc=5.0, scale=2.0, size=(200, 3))
        norm = NormStats.fit(data)
        scaled = np.array([norm.apply(row) for row in data])
        assert np.allclose(scaled.mean(axis=0), 0.0, atol=1e-8)
        assert np.allclose(scaled.std(axis=0), 1.0, atol=1e-8)

    def test_constant_feature_does_not_divide_by_zero(self):
        data = np.ones((10, 2))
        norm = NormStats.fit(data)
        result = norm.apply(np.array([1.0, 1.0]))
        assert np.all(np.isfinite(result))

    def test_save_load_round_trip(self, tmp_path):
        norm = NormStats.fit(np.random.default_rng(2).normal(size=(20, 4)))
        path = tmp_path / "norm.json"
        norm.save(path)
        loaded = NormStats.load(path)
        np.testing.assert_allclose(loaded.mean, norm.mean)
        np.testing.assert_allclose(loaded.std, norm.std)
