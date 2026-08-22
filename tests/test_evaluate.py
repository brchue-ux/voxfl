import numpy as np

from voxfl.benchmark import BenchmarkEntry
from voxfl.corpus import CorpusItem
from voxfl.evaluate import QueryResult, build_index, run_baseline, summarize
from voxfl.retrieval import RetrievalIndex


class StubEmbedder:
    """Maps a fake 'query wav path' straight to a pre-baked vector, so tests
    don't need real audio files to exercise run_baseline()'s wiring."""

    def __init__(self, vectors_by_path):
        self.vectors_by_path = vectors_by_path

    def embed_file(self, path):
        return self.vectors_by_path[path]


def _corpus():
    return [
        CorpusItem(id="bass_a", preset_relpath="Bass/a.vital", role="bass", short_wav="s", long_wav="l"),
        CorpusItem(id="bass_b", preset_relpath="Bass/b.vital", role="bass", short_wav="s", long_wav="l"),
        CorpusItem(id="lead_a", preset_relpath="Lead/a.vital", role="lead", short_wav="s", long_wav="l"),
    ]


def test_summarize_computes_recall_and_mrr():
    results = [
        QueryResult(entry_id="a", role="bass", rank=1),
        QueryResult(entry_id="b", role="bass", rank=3),
        QueryResult(entry_id="c", role="lead", rank=None),
    ]
    report = summarize(results)
    assert report["overall"]["n"] == 3
    assert report["overall"]["recall@1"] == 1 / 3
    assert report["overall"]["recall@5"] == 2 / 3
    assert report["overall"]["mrr"] == (1.0 + 1 / 3 + 0.0) / 3
    assert report["by_role"]["bass"]["n"] == 2
    assert report["by_role"]["lead"]["recall@1"] == 0.0


def test_summarize_empty_results_reports_none():
    assert summarize([]) == {"overall": None, "by_role": {}}


def test_run_baseline_finds_the_exact_match_first_with_identical_vectors():
    items = _corpus()
    index = build_index(items, ["bass_a", "bass_b", "lead_a"], np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]))
    embedder = StubEmbedder({"q_bass_a.wav": np.array([1.0, 0.0])})
    entries = [BenchmarkEntry(id="bass_a", preset_relpath="x", role="bass", preset_wav="p", imitation_wav="q_bass_a.wav")]

    results = run_baseline(entries, index, query_embedder=embedder, role_filter=False)
    assert results[0].rank == 1


def test_run_baseline_skips_entries_without_a_recording():
    items = _corpus()
    index = build_index(items, ["bass_a"], np.array([[1.0, 0.0]]))
    entries = [BenchmarkEntry(id="bass_a", preset_relpath="x", role="bass", preset_wav="p", imitation_wav=None)]
    assert run_baseline(entries, index, query_embedder=None, role_filter=False) == []


def test_run_baseline_role_filter_excludes_wrong_role_candidates():
    items = _corpus()
    # lead_a's vector is closer to the query, but role filtering must confine
    # ranking to bass_a/bass_b — proving 'more candidates in role' can only
    # help, never leak a same-vector match from another role.
    index = build_index(
        items,
        ["bass_a", "bass_b", "lead_a"],
        np.array([[0.0, 1.0], [1.0, 0.0], [1.0, 0.0]]),
    )
    embedder = StubEmbedder({"q.wav": np.array([1.0, 0.0])})
    entries = [BenchmarkEntry(id="bass_a", preset_relpath="x", role="bass", preset_wav="p", imitation_wav="q.wav")]

    results = run_baseline(entries, index, query_embedder=embedder, role_filter=True)
    assert results[0].rank == 2  # bass_b (exact vector match) ranks above bass_a within role


def test_random_baseline_still_produces_a_rank_when_target_in_pool():
    index = RetrievalIndex(ids=["a", "b"], roles={"a": "bass", "b": "bass"}, vectors=None)
    entries = [BenchmarkEntry(id="a", preset_relpath="x", role="bass", preset_wav="p", imitation_wav="q.wav")]
    results = run_baseline(entries, index, query_embedder=None, role_filter=True, seed=1)
    assert results[0].rank in (1, 2)
