import json

import numpy as np
import pytest

from src.models import Chunk
from src.retrieval import build_index, keyword_search, load_index, prepare_evidence, vector_search


def chunk(cid, text, topic="exercise"):
    return Chunk(id=cid, source_id="source", title="Title", url="https://example.org",
                 section="Section", text=text, topic=topic, evidence_type="guidance",
                 published_date="2025-01-01", page=None, scope="Healthy adults",
                 limitations="General guidance")


class Client:
    embedding_model = "fake"
    embedding_digest = "digest-one"
    embedding_prefixes = {"document": "search_document: ", "query": "search_query: "}

    def __init__(self, documents, query=(1., 0.)):
        self.documents = np.asarray(documents, dtype=float)
        self.query = np.asarray([query], dtype=float)
        self.calls = 0

    def embed(self, texts, kind):
        self.calls += 1
        return self.documents if kind == "document" else self.query


def test_bm25_casefold_length_normalization_and_positive_matches():
    items = [chunk("long", "WALK " + "unrelated " * 80), chunk("short", "walk"),
             chunk("none", "sleep")]
    results = keyword_search("WALK!", items)
    assert [r.chunk.id for r in results] == ["short", "long"]
    assert results[0].score > results[1].score > 0


def test_filters_k_empty_query_and_id_ties():
    items = [chunk("b", "walk"), chunk("a", "walk"), chunk("n", "walk", "nutrition")]
    assert [r.chunk.id for r in keyword_search("walk", items, k=1, topic="exercise")] == ["a"]
    assert keyword_search("!!!", items) == []
    assert keyword_search("walk", items, k=0) == []
    assert keyword_search("absent", items) == []


def test_cosine_normalization_filter_and_zero_documents(tmp_path):
    items = [chunk("far", "a"), chunk("close", "b"), chunk("zero", "c"),
             chunk("nutrition", "d", "nutrition")]
    client = Client([[0, 3], [20, 0], [0, 0], [1, 0]])
    index = build_index(items, client, tmp_path)
    assert np.allclose(index.vectors[1], [1, 0])
    results = vector_search("sample", index, client, topic="exercise")
    assert [r.chunk.id for r in results] == ["close", "far"]
    assert [r.score for r in results] == [1., 0.]
    assert vector_search("", index, client) == []
    client.query[:] = 0
    assert vector_search("sample", index, client) == []


def test_vector_tie_is_id_order_and_negative_scores_retained(tmp_path):
    items = [chunk("b", "b"), chunk("a", "a"), chunk("negative", "n")]
    client = Client([[1, 0], [2, 0], [-1, 0]])
    index = build_index(items, client, tmp_path)
    assert [r.chunk.id for r in vector_search("q", index, client)] == ["a", "b", "negative"]


def test_cache_reuse_and_stale_full_metadata_model_and_prefix(tmp_path):
    items = [chunk("a", "walk")]
    client = Client([[1, 0]])
    build_index(items, client, tmp_path)
    build_index(items, client, tmp_path)
    assert client.calls == 1
    changed = [items[0].model_copy(update={"scope": "Different scope"})]
    with pytest.raises(ValueError, match="stale"):
        load_index(changed, client, tmp_path)
    client.embedding_digest = "digest-two"
    with pytest.raises(ValueError, match="stale"):
        load_index(items, client, tmp_path)
    client.embedding_digest = "digest-one"
    client.embedding_prefixes = {"document": "different", "query": "different"}
    with pytest.raises(ValueError, match="stale"):
        load_index(items, client, tmp_path)


def test_reject_shape_nonfinite_and_query_model_mismatch(tmp_path):
    with pytest.raises(ValueError, match="shape"):
        build_index([chunk("a", "x")], Client([[1, 0], [0, 1]]), tmp_path)
    with pytest.raises(ValueError, match="finite"):
        build_index([chunk("a", "x")], Client([[np.nan, 0]]), tmp_path)
    client = Client([[1, 0]])
    index = build_index([chunk("a", "x")], client, tmp_path)
    client.embedding_digest = "changed"
    with pytest.raises(ValueError, match="model"):
        vector_search("q", index, client)


def test_empty_index_and_clipping_retains_metadata_without_mutation(tmp_path):
    client = Client([])
    index = build_index([], client, tmp_path)
    assert vector_search("q", index, client) == []
    assert client.calls == 0
    items = [chunk("a", "one two three four"), chunk("b", "five six")]
    results = keyword_search("one five", items)
    clipped = prepare_evidence(results, max_words=3)
    assert sum(len(r.chunk.text.split()) for r in clipped) == 3
    assert clipped[0].chunk.id == results[0].chunk.id
    assert clipped[0].chunk.scope == "Healthy adults"
    assert clipped[0].chunk.limitations == "General guidance"
    assert [r.chunk.text for r in clipped] == ["five six", "one"]
    assert [r.chunk.text for r in results] == ["five six", "one two three four"]
    assert prepare_evidence(results, max_words=0) == []


def test_evidence_budget_keeps_source_paragraph_boundaries():
    item = chunk("p", "First paragraph.\n\nSecond paragraph with detail.")
    result = prepare_evidence([keyword_search("First", [item])[0]], max_words=20)
    assert result[0].chunk.text == "First paragraph.\n\nSecond paragraph with detail."


def test_cache_tamper_rejected(tmp_path):
    client = Client([[1, 0]])
    items = [chunk("a", "x")]
    build_index(items, client, tmp_path)
    metadata = json.loads((tmp_path / "index.json").read_text())
    metadata["chunks"][0]["limitations"] = "tampered"
    (tmp_path / "index.json").write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="stale|corrupt"):
        load_index(items, client, tmp_path)


def test_stale_build_replaces_cache_and_query_dimension_rejected(tmp_path):
    client = Client([[1, 0]])
    items = [chunk("a", "x")]
    build_index(items, client, tmp_path)
    changed = [chunk("a", "new text")]
    rebuilt = build_index(changed, client, tmp_path)
    assert rebuilt.chunks[0].text == "new text"
    assert load_index(changed, client, tmp_path).corpus_hash == rebuilt.corpus_hash
    client.query = np.array([[1, 0, 0]], dtype=float)
    with pytest.raises(ValueError, match="shape"):
        vector_search("query", rebuilt, client)


def test_cached_vector_corruption_rejected(tmp_path):
    client = Client([[1, 0]])
    items = [chunk("a", "x")]
    build_index(items, client, tmp_path)
    np.save(tmp_path / "vectors.npy", np.array([[0, 1.]]))
    with pytest.raises(ValueError, match="checksum"):
        load_index(items, client, tmp_path)
