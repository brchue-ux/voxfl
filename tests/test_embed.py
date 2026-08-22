import numpy as np
import pytest

from voxfl.embed import RandomEmbedder, cosine_similarity


def test_random_embedder_is_deterministic_per_path():
    embedder = RandomEmbedder(dim=8)
    assert np.array_equal(embedder.embed_file("a.wav"), embedder.embed_file("a.wav"))


def test_random_embedder_differs_across_paths():
    embedder = RandomEmbedder(dim=8)
    assert not np.array_equal(embedder.embed_file("a.wav"), embedder.embed_file("b.wav"))


def test_cosine_similarity_of_identical_vectors_is_one():
    v = np.array([1.0, 2.0, 3.0])
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_of_orthogonal_vectors_is_zero():
    assert cosine_similarity(np.array([1.0, 0.0]), np.array([0.0, 1.0])) == pytest.approx(0.0)


def test_extract_embedding_handles_a_pooler_output_object():
    torch = pytest.importorskip("torch")
    from voxfl.embed import _extract_embedding

    class FakeOutput:
        pooler_output = torch.tensor([[1.0, 2.0, 3.0]])

    result = _extract_embedding(FakeOutput())
    np.testing.assert_allclose(result, [1.0, 2.0, 3.0])


def test_extract_embedding_handles_a_plain_tensor():
    torch = pytest.importorskip("torch")
    from voxfl.embed import _extract_embedding

    tensor = torch.tensor([[4.0, 5.0]])
    result = _extract_embedding(tensor)
    np.testing.assert_allclose(result, [4.0, 5.0])
