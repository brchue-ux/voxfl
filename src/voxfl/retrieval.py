"""Search the corpus — Phase 1 steps 3-4: rank by embedding similarity, or
not at all (the random baseline), optionally restricted to one role.

Brute-force NumPy, per architecture.md's stack table ("a few thousand
presets doesn't need anything clever; brute force is fine until it isn't").
"""

from __future__ import annotations

import numpy as np


class RetrievalIndex:
    """A corpus's ids, roles and embedding matrix for one baseline method."""

    def __init__(self, ids: list[str], roles: dict[str, str], vectors: np.ndarray | None = None):
        self.ids = ids
        self.roles = roles  # id -> role
        self.vectors = vectors  # (N, D) aligned with ids, or None for the random baseline

    def role_mask(self, role: str | None) -> np.ndarray:
        if role is None:
            return np.ones(len(self.ids), dtype=bool)
        return np.array([self.roles.get(i) == role for i in self.ids])

    def rank(self, query: np.ndarray | None, *, role: str | None, rng: np.random.Generator) -> list[str]:
        """Ranked ids, best match first, restricted to ``role`` if given.

        Pass ``query=None`` for the random baseline: a uniform shuffle of the
        candidate set, ignoring embeddings entirely.
        """
        mask = self.role_mask(role)
        candidate_ids = [self.ids[i] for i in np.nonzero(mask)[0]]
        if not candidate_ids:
            return []
        if query is None or self.vectors is None:
            order = rng.permutation(len(candidate_ids))
            return [candidate_ids[i] for i in order]

        candidates = self.vectors[mask]
        sims = _cosine_batch(query, candidates)
        order = np.argsort(-sims, kind="stable")
        return [candidate_ids[i] for i in order]


def _cosine_batch(query: np.ndarray, corpus: np.ndarray) -> np.ndarray:
    query = np.asarray(query, dtype=np.float64)
    corpus = np.asarray(corpus, dtype=np.float64)
    q_norm = np.linalg.norm(query) or 1e-12
    c_norms = np.linalg.norm(corpus, axis=1)
    c_norms = np.where(c_norms < 1e-12, 1e-12, c_norms)
    return (corpus @ query) / (c_norms * q_norm)
