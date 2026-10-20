"""Fixed BM25 and normalized cosine retrieval over the same reviewed chunks.

Scores measure matching/relevance, not truth. Zero document vectors are excluded;
a zero query vector yields no results. Both paths retain provenance on every hit.
"""
from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np

from src.models import Chunk, RetrievedChunk

BM25_K1 = 1.5
BM25_B = 0.75
DEFAULT_PREFIXES = {"document": "search_document: ", "query": "search_query: "}
INDEX_VERSION = 1


def _tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.casefold())


def _rank(chunks, scores, k):
    pairs = sorted(zip(chunks, scores), key=lambda pair: (-float(pair[1]), pair[0].id))
    return [RetrievedChunk(chunk=c, score=float(s)) for c, s in pairs[:max(0, k)]]


def keyword_search(question: str, chunks: list[Chunk], k: int = 3,
                   topic: str | None = None) -> list[RetrievedChunk]:
    terms = set(_tokens(question))
    corpus = [c for c in chunks if topic is None or c.topic == topic]
    if not terms or not corpus or k <= 0:
        return []
    bags = [Counter(_tokens(c.text)) for c in corpus]
    lengths = [sum(bag.values()) for bag in bags]
    average = sum(lengths) / len(corpus)
    if not average:
        return []
    scores = np.zeros(len(corpus), dtype=float)
    for term in sorted(terms):
        df = sum(term in bag for bag in bags)
        if not df:
            continue
        idf = math.log(1 + (len(corpus) - df + .5) / (df + .5))
        for i, bag in enumerate(bags):
            frequency = bag[term]
            denominator = frequency + BM25_K1 * (1 - BM25_B + BM25_B * lengths[i] / average)
            scores[i] += idf * frequency * (BM25_K1 + 1) / denominator
    positive = [(c, s) for c, s in zip(corpus, scores) if s > 0]
    return _rank([p[0] for p in positive], [p[1] for p in positive], k)


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def corpus_fingerprint(chunks: list[Chunk]) -> str:
    # Keep order: embedding row positions must match the caller's exact corpus.
    return hashlib.sha256(_canonical([c.model_dump(mode="json") for c in chunks])).hexdigest()


def _prefixes(client):
    return dict(getattr(client, "embedding_prefixes", DEFAULT_PREFIXES))


def _identity(chunks, client):
    return {"version": INDEX_VERSION, "corpus_hash": corpus_fingerprint(chunks),
            "model_name": client.embedding_model, "model_digest": client.embedding_digest,
            "prefixes": _prefixes(client)}


def _normalize(vectors, rows):
    vectors = np.asarray(vectors, dtype=np.float64)
    if vectors.ndim != 2 or vectors.shape[0] != rows or (rows and not vectors.shape[1]):
        raise ValueError("Embedding shape does not match all input chunks; no truncation is allowed.")
    if not np.isfinite(vectors).all():
        raise ValueError("Embedding vectors must contain only finite values.")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if not np.isfinite(norms).all():
        raise ValueError("Embedding vector norms must be finite.")
    return np.divide(vectors, norms, out=np.zeros_like(vectors), where=norms != 0)


@dataclass
class VectorIndex:
    chunks: list[Chunk]
    vectors: np.ndarray
    corpus_hash: str
    model_digest: str
    model_name: str
    prefixes: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_PREFIXES))


def load_index(chunks: list[Chunk], client, cache_dir: Path) -> VectorIndex:
    """Load only a cache for these exact chunks, model digest and prefix settings."""
    cache_dir = Path(cache_dir)
    try:
        metadata = json.loads((cache_dir / "index.json").read_text(encoding="utf-8"))
        expected = _identity(chunks, client)
        if any(metadata.get(key) != value for key, value in expected.items()):
            raise ValueError("Embedding cache is stale: corpus, model or prefixes changed.")
        stored = [Chunk.model_validate(c) for c in metadata["chunks"]]
        if corpus_fingerprint(stored) != expected["corpus_hash"]:
            raise ValueError("Embedding cache is corrupt: chunk metadata changed.")
        vector_bytes = (cache_dir / "vectors.npy").read_bytes()
        if hashlib.sha256(vector_bytes).hexdigest() != metadata["vectors_hash"]:
            raise ValueError("Embedding cache is corrupt: vector checksum mismatch.")
        vectors = np.load(cache_dir / "vectors.npy", allow_pickle=False)
        normalized = _normalize(vectors, len(chunks))
        if not np.allclose(vectors, normalized, atol=1e-10):
            raise ValueError("Embedding cache is corrupt: vectors are not normalized.")
    except (KeyError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Embedding cache is corrupt: invalid metadata.") from exc
    return VectorIndex(list(chunks), vectors, expected["corpus_hash"],
                       expected["model_digest"], expected["model_name"], expected["prefixes"])


def build_index(chunks: list[Chunk], client, cache_dir: Path) -> VectorIndex:
    """Reuse a matching cache or rebuild stale data through document embeddings."""
    cache_dir = Path(cache_dir)
    if len({c.id for c in chunks}) != len(chunks):
        raise ValueError("Chunk IDs must be unique.")
    if (cache_dir / "index.json").exists():
        try:
            return load_index(chunks, client, cache_dir)
        except (ValueError, OSError):
            pass  # Reject stale/corrupt rows, never silently use them.
    identity = _identity(chunks, client)
    vectors = (_normalize(client.embed([c.text for c in chunks], kind="document"), len(chunks))
               if chunks else np.empty((0, 0), dtype=np.float64))
    index = VectorIndex(list(chunks), vectors, identity["corpus_hash"], identity["model_digest"],
                        identity["model_name"], identity["prefixes"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Metadata is written last; a partial replacement fails its checksum on the next load.
    np.save(cache_dir / "vectors.npy", vectors, allow_pickle=False)
    metadata = {**identity, "chunks": [c.model_dump(mode="json") for c in chunks],
                "vectors_hash": hashlib.sha256((cache_dir / "vectors.npy").read_bytes()).hexdigest()}
    (cache_dir / "index.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return index


def vector_search(question: str, index: VectorIndex, client, k: int = 3,
                  topic: str | None = None) -> list[RetrievedChunk]:
    if (index.model_name != client.embedding_model or index.model_digest != client.embedding_digest
            or index.prefixes != _prefixes(client)):
        raise ValueError("Query embedding model/digest/prefixes do not match the index.")
    if index.corpus_hash != corpus_fingerprint(index.chunks):
        raise ValueError("Index corpus is stale: chunk metadata changed.")
    if not _tokens(question) or not index.chunks or k <= 0:
        return []
    query = _normalize(client.embed([question], kind="query"), 1)
    if query.shape[1] != index.vectors.shape[1]:
        raise ValueError("Query embedding shape differs from the document index.")
    if not np.any(query):
        return []
    selected = [i for i, c in enumerate(index.chunks)
                if (topic is None or c.topic == topic) and np.any(index.vectors[i])]
    if not selected:
        return []
    scores = index.vectors[selected] @ query[0]
    return _rank([index.chunks[i] for i in selected], scores, k)


def prepare_evidence(results: list[RetrievedChunk], max_words: int = 650) -> list[RetrievedChunk]:
    """Apply a shared text-word budget while retaining IDs, scope and caveats.

    Metadata is not dropped to make space; max_words covers excerpt text only.
    Clipped entries are copies, so retrieval metrics retain the full original hits.
    """
    remaining = max(0, max_words)
    evidence = []
    for result in results:
        if not remaining:
            break
        words = list(re.finditer(r"\S+", result.chunk.text))
        if not words:
            continue
        selected_count = min(remaining, len(words))
        excerpt = result.chunk.text[:words[selected_count - 1].end()].rstrip()
        copy = result.chunk.model_copy(update={"text": excerpt})
        evidence.append(RetrievedChunk(chunk=copy, score=result.score))
        remaining -= selected_count
    return evidence
