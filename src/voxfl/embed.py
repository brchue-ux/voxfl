"""Embedders — turn a rendered preset (or a vocal query) into a vector that
can be compared across modalities. One class per
[architecture.md](../../docs/architecture.md#2-query-embedding--the-hard-part)
baseline, in the order [evaluation.md](../../docs/evaluation.md#baselines-in-order)
says to build and measure them.

Every embedder implements ``embed_file(path) -> np.ndarray``, so
``corpus.py``/``evaluate.py`` don't need to know which baseline they're
holding.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

import numpy as np

from .features import NormStats, features_from_file


class Embedder(Protocol):
    name: str

    def embed_file(self, path: str) -> np.ndarray: ...


class RandomEmbedder:
    """Not a real baseline embedder — see ``retrieval.rank_random`` instead,
    which ranks without any vector at all. Kept only so ``corpus.py``'s
    "one embedder per method" pipeline has something to call for ``method
    random`` when a caller wants a vector anyway (e.g. to sanity-check the
    plumbing). Deterministic per path, not per run, so results are reproducible.
    """

    name = "random"

    def __init__(self, dim: int = 16):
        self.dim = dim

    def embed_file(self, path: str) -> np.ndarray:
        digest = hashlib.sha256(str(path).encode()).digest()
        seed = int.from_bytes(digest[:8], "little")
        rng = np.random.default_rng(seed)
        return rng.normal(size=self.dim)


class FeatureEmbedder:
    """Baseline 2: hand-crafted timbral features, domain-normalised.

    ``norm`` must be fit on the *matching* corpus — the preset corpus for
    embedding rendered presets, the vocal-query corpus for embedding
    imitations — per architecture.md's domain-normalisation note. Passing the
    wrong one silently produces comparable-looking numbers that mean nothing.
    """

    name = "features"

    def __init__(self, norm: NormStats):
        self.norm = norm

    def embed_file(self, path: str) -> np.ndarray:
        return self.norm.apply(features_from_file(path))


class ClapUnavailable(Exception):
    """Raised when the optional CLAP dependency isn't installed."""


class ClapEmbedder:
    """Baseline 3: LAION CLAP's audio tower, via the ``transformers`` port.

    Not a required dependency of this package — ``pip install transformers
    torch`` (or ``laion-clap``) to use it. Model weights (~2.5 GB) download on
    first use, from HuggingFace, so this needs network access at least once.
    See docs/phase1.md for exact instructions if that isn't available where
    this runs.
    """

    name = "clap"

    def __init__(self, model_name: str = "laion/clap-htsat-unfused", device: str = "cpu"):
        try:
            import torch  # noqa: PLC0415
            from transformers import ClapModel, ClapProcessor  # noqa: PLC0415
        except ImportError as exc:
            raise ClapUnavailable(
                "CLAP baseline needs 'transformers' and 'torch'. "
                "Install with: pip install transformers torch"
            ) from exc

        self._torch = torch
        self.device = device
        self.model = ClapModel.from_pretrained(model_name).to(device).eval()
        self.processor = ClapProcessor.from_pretrained(model_name)
        self.sample_rate = self.processor.feature_extractor.sampling_rate

    def embed_file(self, path: str) -> np.ndarray:
        from .features import load_mono  # noqa: PLC0415

        mono, rate = load_mono(path)
        if rate != self.sample_rate:
            mono = _resample(mono, rate, self.sample_rate)
        # transformers renamed ClapProcessor's audio kwarg from 'audios' to
        # 'audio' at some point; accept either installed version.
        try:
            inputs = self.processor(
                audio=mono, sampling_rate=self.sample_rate, return_tensors="pt"
            ).to(self.device)
        except (TypeError, ValueError):
            inputs = self.processor(
                audios=mono, sampling_rate=self.sample_rate, return_tensors="pt"
            ).to(self.device)
        with self._torch.no_grad():
            out = self.model.get_audio_features(**inputs)
        return _extract_embedding(out)

    def embed_text(self, text: str) -> np.ndarray:
        """CLAP's other tower — not used by Phase 1's retrieval baselines
        (those are all vocal-audio queries), but wired up because it's the
        entire reason architecture.md picks CLAP: word-based search reaches
        the same embedding space for free once this baseline exists.
        """
        inputs = self.processor(text=[text], return_tensors="pt").to(self.device)
        with self._torch.no_grad():
            out = self.model.get_text_features(**inputs)
        return _extract_embedding(out)


def _extract_embedding(out) -> np.ndarray:
    """get_audio_features()/get_text_features() return a plain (batch, dim)
    tensor on older `transformers`, and a BaseModelOutputWithPooling on
    newer ones (>=4.5x) — pull the projected embedding out of either."""
    tensor = out.pooler_output if hasattr(out, "pooler_output") else out
    return tensor[0].detach().cpu().numpy().astype(np.float64)


def _resample(mono: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate == to_rate:
        return mono
    duration = len(mono) / from_rate
    n_out = int(round(duration * to_rate))
    x_old = np.linspace(0.0, duration, num=len(mono), endpoint=False)
    x_new = np.linspace(0.0, duration, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, mono)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1e-12
    return float(np.dot(a, b) / denom)
