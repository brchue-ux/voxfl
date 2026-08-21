"""Synthetic corpus + vocal-imitation generator.

Exists for exactly one reason: validate the Phase 1 pipeline end-to-end
(harness -> render/embed -> baselines -> role filtering -> metrics) on this
machine, which has neither DawDreamer/Vital installed nor the captain's own
voice recorded. See docs/phase1.md.

**Not a substitute for the real corpus or real recordings** — it is
additive-synthesis noise standing in for both, correlated only on the axes
that matter (brightness, noisiness, attack, decay) the way a real vocal
imitation and a real preset are meant to correlate. Every report generated
from this data is labelled "synthetic" so it can never be mistaken for a
result against the captain's own voice.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .render import write_wav

SAMPLE_RATE = 22050  # plenty for this synthesis, and 2x smaller files than 44.1k

ROLES = ("bass", "lead", "pad", "pluck")

# (freq_lo, freq_hi), (brightness_lo, hi), (noise_lo, hi), (attack_lo, hi), (decay_lo, hi)
ROLE_PROFILES = {
    "bass": dict(freq=(55, 110), brightness=(0.1, 0.4), noise=(0.0, 0.1), attack=(0.005, 0.03), decay=(0.6, 2.5)),
    "lead": dict(freq=(220, 660), brightness=(0.5, 0.95), noise=(0.0, 0.15), attack=(0.002, 0.02), decay=(0.3, 1.2)),
    "pad": dict(freq=(110, 330), brightness=(0.2, 0.6), noise=(0.05, 0.25), attack=(0.3, 1.0), decay=(1.5, 4.0)),
    "pluck": dict(freq=(165, 440), brightness=(0.4, 0.85), noise=(0.0, 0.1), attack=(0.001, 0.01), decay=(0.15, 0.6)),
}


@dataclass
class SynthParams:
    freq: float
    brightness: float  # 0..1 — higher keeps more high-harmonic energy
    noise: float  # 0..1 — noise mixed in with the harmonic tone
    attack: float  # seconds
    decay: float  # seconds, exponential time constant


def sample_params(role: str, rng: np.random.Generator) -> SynthParams:
    p = ROLE_PROFILES[role]
    return SynthParams(
        freq=rng.uniform(*p["freq"]),
        brightness=rng.uniform(*p["brightness"]),
        noise=rng.uniform(*p["noise"]),
        attack=rng.uniform(*p["attack"]),
        decay=rng.uniform(*p["decay"]),
    )


def _envelope(t: np.ndarray, attack: float, decay: float) -> np.ndarray:
    env = np.where(t < attack, t / max(attack, 1e-6), np.exp(-(t - attack) / max(decay, 1e-6)))
    return np.clip(env, 0.0, 1.0)


def synth_tone(
    params: SynthParams, duration: float, rng: np.random.Generator, sample_rate: int = SAMPLE_RATE
) -> np.ndarray:
    """A crude additive-synthesis "preset": harmonic stack + noise, shaped by
    an attack/decay envelope. Brightness sets how fast harmonic amplitude
    rolls off with harmonic number.
    """
    t = np.arange(int(duration * sample_rate)) / sample_rate
    n_harmonics = 20
    rolloff = 0.15 + 0.83 * params.brightness  # low brightness -> fast rolloff, high -> slow
    tone = np.zeros_like(t)
    for h in range(1, n_harmonics + 1):
        amp = (rolloff ** (h - 1)) / h
        tone += amp * np.sin(2 * np.pi * params.freq * h * t)
    tone /= np.abs(tone).max() + 1e-9

    noise = rng.normal(size=t.shape)
    noise /= np.abs(noise).max() + 1e-9

    signal = (1 - params.noise) * tone + params.noise * noise
    signal *= _envelope(t, params.attack, params.decay)
    peak = np.abs(signal).max()
    return signal / peak if peak > 1e-9 else signal


def imitation_params(target: SynthParams, rng: np.random.Generator) -> SynthParams:
    """A "vocal imitation" of ``target``: human vocal register regardless of
    the target's actual pitch, correlated but jittered on the axes a person
    can actually control by mouth (brightness, noise, attack, decay) — the
    same "alike only in the ways meant to be alike" relationship
    architecture.md describes for real voice vs. a real synth.
    """
    return SynthParams(
        freq=rng.uniform(90, 300),
        brightness=float(np.clip(target.brightness + rng.normal(0, 0.12), 0.02, 1.0)),
        noise=float(np.clip(target.noise * 0.6 + rng.uniform(0, 0.15), 0.0, 1.0)),
        attack=max(0.001, target.attack + rng.normal(0, target.attack * 0.4 + 0.01)),
        decay=max(0.05, target.decay * rng.uniform(0.4, 0.9)),
    )


@dataclass
class SyntheticPreset:
    id: str
    role: str
    params: SynthParams


def build_synthetic_corpus(
    root: Path, *, per_role: int = 15, seed: int = 0
) -> tuple[list[SyntheticPreset], Path, Path]:
    """Writes short/long wav trees under ``root`` shaped exactly like two
    ``voxfl.vital batch`` runs (role/<id>.wav), so corpus.build_manifest()
    can consume them unmodified. Returns (presets, short_dir, long_dir).
    """
    rng = np.random.default_rng(seed)
    short_dir, long_dir = Path(root) / "short", Path(root) / "long"
    presets = []
    for role in ROLES:
        for i in range(per_role):
            preset_id = f"{role}_{i:02d}"
            params = sample_params(role, rng)
            presets.append(SyntheticPreset(id=preset_id, role=role, params=params))
            write_wav(short_dir / role / f"{preset_id}.wav", synth_tone(params, 0.5, rng, SAMPLE_RATE)[None, :], SAMPLE_RATE)
            write_wav(long_dir / role / f"{preset_id}.wav", synth_tone(params, 1.8, rng, SAMPLE_RATE)[None, :], SAMPLE_RATE)
    return presets, short_dir, long_dir


def build_synthetic_benchmark(
    presets: list[SyntheticPreset], root: Path, *, per_role: int | None = None, seed: int = 1
) -> Path:
    """Writes one imitation wav per chosen preset under ``root/recordings/<id>.wav``
    — the shape benchmark.ingest() expects. Returns the recordings dir.
    """
    rng = np.random.default_rng(seed)
    recordings = Path(root) / "recordings"
    by_role: dict[str, list[SyntheticPreset]] = {}
    for p in presets:
        by_role.setdefault(p.role, []).append(p)

    for role, items in by_role.items():
        chosen = items if per_role is None else items[: per_role]
        for preset in chosen:
            imit = imitation_params(preset.params, rng)
            duration = rng.uniform(0.8, 1.6)
            audio = synth_tone(imit, duration, rng, SAMPLE_RATE)
            write_wav(recordings / f"{preset.id}.wav", audio[None, :], SAMPLE_RATE)
    return recordings
