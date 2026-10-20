"""Load reviewed, offline section snapshots and create deterministic chunks."""
import hashlib
import json
import re
from pathlib import Path

from src.models import Chunk, Document


def clean_text(text: str) -> str:
    return '\n\n'.join(' '.join(p.split()) for p in re.split(r'\n\s*\n', text.strip()) if p.strip())


def load_documents(path: Path) -> list[Document]:
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or not isinstance(payload.get('documents'), list):
        raise ValueError('Snapshot must contain a documents list')
    documents = []
    seen = set()
    for record in payload['documents']:
        value = dict(record)
        for field in ('source_id', 'title', 'url', 'section', 'text', 'topic', 'evidence_type', 'accessed_date', 'license', 'scope', 'limitations'):
            if not isinstance(value.get(field), str) or not value[field].strip():
                raise ValueError(f'Missing or empty document {field}')
        value['text'] = clean_text(value['text'])
        document = Document(**value)
        identity = (document.source_id, document.section)
        if identity in seen:
            raise ValueError(f'Duplicate source section: {identity}')
        seen.add(identity)
        documents.append(document)
    return documents


def chunk_documents(documents: list[Document], max_words: int = 180) -> list[Chunk]:
    if type(max_words) is not int or max_words <= 0:
        raise ValueError('max_words must be a positive integer')
    chunks = []
    for document in documents:
        parts, current = [], []
        current_words = 0
        for paragraph in clean_text(document.text).split('\n\n'):
            words = paragraph.split()
            if current and current_words + len(words) > max_words:
                parts.append('\n\n'.join(current))
                current, current_words = [], 0
            while len(words) > max_words:
                parts.append(' '.join(words[:max_words]))
                words = words[max_words:]
            if words:
                current.append(' '.join(words))
                current_words += len(words)
        if current:
            parts.append('\n\n'.join(current))
        for position, text in enumerate(parts):
            metadata = document.model_dump(mode='json',exclude={'license'})
            metadata['text'] = text
            # Include every grounding field, so scope edits cannot reuse stale IDs.
            identity = json.dumps({'position': position, 'chunk': metadata}, sort_keys=True, ensure_ascii=False)
            digest = hashlib.sha256(identity.encode('utf-8')).hexdigest()[:20]
            chunks.append(Chunk(id=f'{document.source_id}-{digest}', **metadata))
    return chunks
