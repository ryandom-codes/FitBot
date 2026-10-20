"""Build/reuse the reviewed corpus index using the configured local embedding model."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_settings
from src.ingestion import chunk_documents, load_documents
from src.llm import LocalModelClient
from src.retrieval import build_index


def main():
    settings = load_settings()
    documents = load_documents(settings.project_root / "data" / "sources.json")
    chunks = chunk_documents(documents)
    client = LocalModelClient(settings)
    index = build_index(chunks, client, settings.cache_dir)
    print(f"Indexed {len(index.chunks)} reviewed chunks; model={index.model_name}")
    print(f"Corpus SHA256: {index.corpus_hash}")
    print(f"Embedding digest: {index.model_digest}")


if __name__ == "__main__":
    main()
