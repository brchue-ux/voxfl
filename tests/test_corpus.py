from pathlib import Path

import numpy as np
import pytest

from voxfl.corpus import (
    CorpusItem,
    build_manifest,
    embed_manifest,
    fit_feature_norm,
    load_embeddings,
    load_manifest,
    role_counts,
    role_from_path,
    save_embeddings,
    save_manifest,
)
from voxfl.embed import FeatureEmbedder, RandomEmbedder
from voxfl.render import write_wav

SR = 22050


def _write(path: Path, freq=220.0, duration=0.3):
    t = np.arange(int(duration * SR)) / SR
    write_wav(path, np.sin(2 * np.pi * freq * t)[None, :], SR)


@pytest.mark.parametrize(
    "relpath,expected",
    [
        ("Bass/sub_growl.wav", "bass"),
        ("Leads/pluckylead.wav", "lead"),
        ("pad/warm.wav", "pad"),
        ("Plucks/pizz.wav", "pluck"),
        ("Misc/weird.wav", "other"),
    ],
)
def test_role_from_path(relpath, expected):
    assert role_from_path(relpath) == expected


def test_build_manifest_pairs_short_and_long_and_tags_role(tmp_path):
    short, long_ = tmp_path / "short", tmp_path / "long"
    _write(short / "Bass" / "growl.wav")
    _write(long_ / "Bass" / "growl.wav")
    _write(short / "Lead" / "buzz.wav")
    # Lead/buzz has no long variant — must still appear.

    items = build_manifest(short, long_)
    by_id = {i.id: i for i in items}
    assert len(items) == 2
    growl = by_id["Bass__growl"]
    assert growl.role == "bass"
    assert growl.short_wav and growl.long_wav
    buzz = by_id["Lead__buzz"]
    assert buzz.role == "lead"
    assert buzz.short_wav and buzz.long_wav is None


def test_manifest_save_load_round_trip(tmp_path):
    items = [CorpusItem(id="a", preset_relpath="Bass/a.vital", role="bass", short_wav="s.wav", long_wav=None)]
    path = save_manifest(items, tmp_path / "manifest.jsonl")
    loaded = load_manifest(path)
    assert loaded == items


def test_role_counts():
    items = [
        CorpusItem(id="1", preset_relpath="x", role="bass", short_wav="s", long_wav=None),
        CorpusItem(id="2", preset_relpath="y", role="bass", short_wav="s", long_wav=None),
        CorpusItem(id="3", preset_relpath="z", role="pad", short_wav="s", long_wav=None),
    ]
    counts = role_counts(items)
    assert counts["bass"] == 2
    assert counts["pad"] == 1
    assert counts["lead"] == 0


def test_embed_manifest_with_random_embedder_gives_one_vector_per_item(tmp_path):
    short, long_ = tmp_path / "short", tmp_path / "long"
    _write(short / "Bass" / "a.wav")
    _write(long_ / "Bass" / "a.wav")
    items = build_manifest(short, long_)

    ids, vectors = embed_manifest(items, RandomEmbedder(dim=8))
    assert ids == ["Bass__a"]
    assert vectors.shape == (1, 8)


def test_embed_manifest_is_deterministic_for_random_embedder(tmp_path):
    short = tmp_path / "short"
    _write(short / "Bass" / "a.wav")
    items = build_manifest(short, tmp_path / "empty_long")

    embedder = RandomEmbedder(dim=4)
    _, v1 = embed_manifest(items, embedder)
    _, v2 = embed_manifest(items, embedder)
    np.testing.assert_array_equal(v1, v2)


def test_fit_feature_norm_and_embed_features(tmp_path):
    short, long_ = tmp_path / "short", tmp_path / "long"
    _write(short / "Bass" / "a.wav", freq=110)
    _write(long_ / "Bass" / "a.wav", freq=110)
    _write(short / "Lead" / "b.wav", freq=880)
    _write(long_ / "Lead" / "b.wav", freq=880)
    items = build_manifest(short, long_)

    norm = fit_feature_norm(items)
    embedder = FeatureEmbedder(norm)
    ids, vectors = embed_manifest(items, embedder)
    assert len(ids) == 2
    assert vectors.shape[0] == 2
    assert np.all(np.isfinite(vectors))


def test_embeddings_save_load_round_trip(tmp_path):
    ids = ["a", "b"]
    vectors = np.array([[1.0, 2.0], [3.0, 4.0]])
    path = save_embeddings(ids, vectors, tmp_path / "emb.npz")
    loaded_ids, loaded_vectors = load_embeddings(path)
    assert loaded_ids == ids
    np.testing.assert_array_equal(loaded_vectors, vectors)
