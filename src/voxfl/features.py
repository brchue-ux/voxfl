"""Hand-crafted timbral features — Phase 1 baseline 2.

[architecture.md](../../docs/architecture.md#2-query-embedding--the-hard-part)
step 2a: brightness, noisiness, attack time, decay shape, harmonicity and
spectral flux, crude on their own but made comparable across modalities by
z-scoring vocal queries against a corpus of vocal queries and presets against
the preset corpus (:class:`NormStats`) — "the brightest sound I can make"
then lands near "a bright preset" even though the absolute numbers involved
share nothing.

Deliberately no ``librosa`` dependency: everything here is a handful of FFT
frames and NumPy reductions, which is all six features need.
"""

from __future__ import annotations

import json
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FEATURE_NAMES = (
    "centroid",
    "noisiness",
    "attack_time",
    "decay_slope",
    "harmonicity",
    "flux",
)

FRAME_SIZE = 2048
HOP_SIZE = 512


class FeatureError(Exception):
    """Raised when a feature vector cannot be computed."""


def load_mono(path: str | Path) -> tuple[np.ndarray, int]:
    """Read a wav file (as written by ``render.write_wav``) as mono float64 in [-1, 1]."""
    path = Path(path)
    with wave.open(str(path), "rb") as fh:
        channels = fh.getnchannels()
        rate = fh.getframerate()
        width = fh.getsampwidth()
        n = fh.getnframes()
        raw = fh.readframes(n)
    if width != 2:
        raise FeatureError(f"{path}: expected 16-bit PCM, got {width * 8}-bit")
    data = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, rate


def _frames(mono: np.ndarray) -> np.ndarray:
    """Overlapping analysis frames, Hann-windowed. Shape (n_frames, FRAME_SIZE)."""
    if len(mono) < FRAME_SIZE:
        mono = np.pad(mono, (0, FRAME_SIZE - len(mono)))
    n_frames = 1 + (len(mono) - FRAME_SIZE) // HOP_SIZE
    window = np.hanning(FRAME_SIZE)
    idx = np.arange(FRAME_SIZE)[None, :] + HOP_SIZE * np.arange(n_frames)[:, None]
    return mono[idx] * window[None, :]


def raw_features(mono: np.ndarray, sample_rate: int) -> np.ndarray:
    """The six timbral features, in raw (un-normalised) units. See FEATURE_NAMES."""
    mono = np.asarray(mono, dtype=np.float64)
    if not np.any(np.abs(mono) > 1e-9):
        return np.zeros(len(FEATURE_NAMES), dtype=np.float64)

    frames = _frames(mono)
    spectrum = np.abs(np.fft.rfft(frames, axis=1))
    freqs = np.fft.rfftfreq(FRAME_SIZE, d=1.0 / sample_rate)
    power = spectrum**2
    total_power = power.sum(axis=1) + 1e-12

    # Brightness: energy-weighted mean frequency, averaged over frames with signal.
    active = total_power > total_power.max() * 1e-4
    centroid_per_frame = (power * freqs[None, :]).sum(axis=1) / total_power
    centroid = float(centroid_per_frame[active].mean()) if active.any() else 0.0

    # Noisiness: spectral flatness (geometric mean / arithmetic mean of the spectrum).
    log_spec = np.log(spectrum + 1e-12)
    geo_mean = np.exp(log_spec.mean(axis=1))
    arith_mean = spectrum.mean(axis=1) + 1e-12
    flatness = geo_mean / arith_mean
    noisiness = float(flatness[active].mean()) if active.any() else 0.0

    # Attack time: seconds from onset to the envelope's peak.
    envelope = np.sqrt(power.sum(axis=1))
    peak_idx = int(np.argmax(envelope))
    onset_thresh = envelope.max() * 0.05
    above = np.nonzero(envelope[: peak_idx + 1] >= onset_thresh)[0]
    onset_idx = int(above[0]) if above.size else 0
    attack_time = float((peak_idx - onset_idx) * HOP_SIZE / sample_rate)

    # Decay shape: slope of log-energy from the peak to the tail, fit by least squares.
    tail = envelope[peak_idx:]
    if len(tail) >= 2:
        log_tail = np.log(tail + 1e-9)
        t = np.arange(len(tail), dtype=np.float64)
        slope = float(np.polyfit(t, log_tail, 1)[0])
    else:
        slope = 0.0

    # Harmonicity: how much energy sits at integer multiples of the strongest low bin,
    # vs. total energy — a cheap proxy, not a real pitch-tracked harmonic-to-noise ratio.
    mean_spectrum = power.mean(axis=0)
    search = mean_spectrum[(freqs >= 40) & (freqs <= 2000)]
    search_freqs = freqs[(freqs >= 40) & (freqs <= 2000)]
    if search.size and search.max() > 0:
        f0 = float(search_freqs[int(np.argmax(search))])
        harmonic_bins = np.zeros_like(freqs, dtype=bool)
        for h in range(1, 12):
            target = f0 * h
            if target > freqs[-1]:
                break
            harmonic_bins |= np.abs(freqs - target) < (freqs[1] - freqs[0]) * 1.5
        harmonicity = float(mean_spectrum[harmonic_bins].sum() / (mean_spectrum.sum() + 1e-12))
    else:
        harmonicity = 0.0

    # Spectral flux: average frame-to-frame spectral change (movement / brightness change).
    if spectrum.shape[0] >= 2:
        norm = spectrum / (np.linalg.norm(spectrum, axis=1, keepdims=True) + 1e-12)
        flux = float(np.linalg.norm(np.diff(norm, axis=0), axis=1).mean())
    else:
        flux = 0.0

    return np.array(
        [centroid, noisiness, attack_time, slope, harmonicity, flux], dtype=np.float64
    )


def features_from_file(path: str | Path) -> np.ndarray:
    mono, rate = load_mono(path)
    return raw_features(mono, rate)


@dataclass
class NormStats:
    """Per-feature z-score stats, fit separately for the preset corpus and the
    vocal-query corpus — see the module docstring for why they must not share stats.
    """

    mean: np.ndarray
    std: np.ndarray

    @classmethod
    def fit(cls, vectors: np.ndarray) -> "NormStats":
        vectors = np.asarray(vectors, dtype=np.float64)
        mean = vectors.mean(axis=0)
        std = vectors.std(axis=0)
        std = np.where(std < 1e-9, 1.0, std)
        return cls(mean=mean, std=std)

    def apply(self, vector: np.ndarray) -> np.ndarray:
        return (np.asarray(vector, dtype=np.float64) - self.mean) / self.std

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"mean": self.mean.tolist(), "std": self.std.tolist()}, indent=2)
        )

    @classmethod
    def load(cls, path: str | Path) -> "NormStats":
        data = json.loads(Path(path).read_text())
        return cls(mean=np.array(data["mean"]), std=np.array(data["std"]))
