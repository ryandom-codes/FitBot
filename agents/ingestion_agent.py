"""Load and chunk the reviewed corpus before retrieval."""
from src.ingestion import load_documents, chunk_documents


def ingest(source_path):
    return chunk_documents(load_documents(source_path))
