import numpy as np
import pytest

from voxfl.retrieval import RetrievalIndex


@pytest.fixture
def index():
    ids = ["bass_a", "bass_b", "lead_a", "pad_a"]
    roles = {"bass_a": "bass", "bass_b": "bass", "lead_a": "lead", "pad_a": "pad"}
    vectors = np.array(
        [
            [1.0, 0.0],  # bass_a
            [0.9, 0.1],  # bass_b — close to bass_a
            [0.0, 1.0],  # lead_a
            [-1.0, 0.0],  # pad_a
        ]
    )
    return RetrievalIndex(ids=ids, roles=roles, vectors=vectors)


def test_rank_orders_by_cosine_similarity_best_first(index):
    query = np.array([1.0, 0.0])
    ranked = index.rank(query, role=None, rng=np.random.default_rng(0))
    assert ranked[0] == "bass_a"
    assert ranked[1] == "bass_b"


def test_role_filter_restricts_candidates(index):
    query = np.array([1.0, 0.0])
    ranked = index.rank(query, role="bass", rng=np.random.default_rng(0))
    assert set(ranked) == {"bass_a", "bass_b"}


def test_role_filter_with_no_matches_returns_empty(index):
    ranked = index.rank(np.array([1.0, 0.0]), role="pluck", rng=np.random.default_rng(0))
    assert ranked == []


def test_query_none_shuffles_instead_of_ranking(index):
    rng = np.random.default_rng(0)
    ranked = index.rank(None, role=None, rng=rng)
    assert set(ranked) == set(index.ids)
    # A shuffle over 4 items landing in exactly similarity order by chance
    # would be a 1/24 coincidence; assert it's *not* deterministically ranked.
    orders = {tuple(index.rank(None, role=None, rng=np.random.default_rng(s))) for s in range(10)}
    assert len(orders) > 1


def test_random_baseline_works_without_a_vectors_matrix():
    index = RetrievalIndex(ids=["a", "b", "c"], roles={"a": "bass", "b": "bass", "c": "lead"}, vectors=None)
    ranked = index.rank(None, role="bass", rng=np.random.default_rng(0))
    assert set(ranked) == {"a", "b"}
