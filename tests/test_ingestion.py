"""Behavioral checks for reviewed-source loading and lossless chunking."""
import importlib.util
import json

import pytest


def api():
    assert importlib.util.find_spec('src.ingestion') is not None, 'Reviewed ingestion API is missing'
    from src.ingestion import chunk_documents, load_documents
    return load_documents, chunk_documents


def record(**changes):
    value = dict(source_id='review', title='Reviewed evidence', url='https://example.gov/review',
                 section='Results', text='First finding.\n\nSecond finding.', topic='strength',
                 evidence_type='systematic_review_meta_analysis', published_date='2026-04-17',
                 accessed_date='2026-10-07', license='CC BY 4.0', scope='Healthy adult beginners',
                 limitations='Group findings cannot predict an individual.', doi='10.1234/review', page=None)
    value.update(changes)
    return value


def write_snapshot(tmp_path, records):
    path = tmp_path / 'sources.json'
    path.write_text(json.dumps({'documents': records}), encoding='utf-8')
    return path


def test_normalizes_whitespace_without_changing_words(tmp_path):
    load, chunk = api()
    docs = load(write_snapshot(tmp_path, [record(text='  A  finding. \n\n Another\t finding. ')]))
    assert docs[0].text == 'A finding.\n\nAnother finding.'
    assert ' '.join(c.text for c in chunk(docs)).split() == ['A', 'finding.', 'Another', 'finding.']


@pytest.mark.parametrize('field,value', [('url', ''), ('section', ''), ('evidence_type', ''), ('source_id', ''), ('text', '')])
def test_rejects_missing_provenance_or_empty_content(tmp_path, field, value):
    load, _ = api()
    with pytest.raises(ValueError):
        load(write_snapshot(tmp_path, [record(**{field: value})]))


def test_rejects_duplicate_source_section(tmp_path):
    load, _ = api()
    with pytest.raises(ValueError, match='Duplicate'):
        load(write_snapshot(tmp_path, [record(), record()]))


def test_long_paragraph_splits_without_loss_and_carries_scope(tmp_path):
    load, chunk = api()
    words = [f'word{i}' for i in range(403)]
    docs = load(write_snapshot(tmp_path, [record(text=' '.join(words))]))
    chunks = chunk(docs, max_words=180)
    assert [len(c.text.split()) for c in chunks] == [180, 180, 43]
    assert ' '.join(c.text for c in chunks).split() == words
    assert all(c.scope == docs[0].scope and c.limitations == docs[0].limitations for c in chunks)
    assert all(c.source_id == 'review' and c.section == 'Results' for c in chunks)


def test_ids_stable_under_unrelated_document_reordering(tmp_path):
    load, chunk = api()
    a, b = record(), record(source_id='other', section='Methods', text='Different content.')
    first = chunk(load(write_snapshot(tmp_path, [a, b])))
    second = chunk(load(write_snapshot(tmp_path, [b, a])))
    assert {c.id: c.text for c in first} == {c.id: c.text for c in second}
    changed = chunk(load(write_snapshot(tmp_path, [record(text='Changed content.')])))[0]
    assert changed.id != first[0].id


def test_never_combines_sections_even_when_small(tmp_path):
    load, chunk = api()
    chunks = chunk(load(write_snapshot(tmp_path, [record(text='Result.'), record(section='Limitations', text='Caution.')])) )
    assert [(c.section, c.text) for c in chunks] == [('Results', 'Result.'), ('Limitations', 'Caution.')]


@pytest.mark.parametrize('limit', [0, -1, True, 1.5])
def test_rejects_invalid_word_budget(limit):
    _, chunk = api()
    with pytest.raises(ValueError):
        chunk([], max_words=limit)


def test_extractor_keeps_selected_paragraphs_but_not_images_or_next_section():
    assert importlib.util.find_spec('scripts.fetch_sources') is not None, 'Reviewed fetcher missing'
    from scripts.fetch_sources import extract_section
    html = '<main><h1>Title</h1><h2>Keep</h2><p>A <a href="x">linked</a> fact.</p><ul><li>One item.</li></ul><img alt="Exclude"><h2>Next</h2><p>Exclude me.</p></main>'
    assert extract_section(html, 'Keep') == 'A linked fact.\n\nOne item.'
    with pytest.raises(ValueError, match='heading'):
        extract_section(html, 'Absent')


def test_sleep_extractor_can_preserve_age_rows_from_recommendation_table():
    from scripts.fetch_sources import extract_section
    html='<main><h2>Getting enough sleep</h2><p>Needs vary with age.</p><table><tr><th>Age</th><th>Hours</th></tr><tr><td>18–60</td><td>7 or more</td></tr></table><h2>Next</h2></main>'
    assert extract_section(html,'Getting enough sleep',include_table_rows=True)=='Needs vary with age.\n\nAge | Hours\n\n18–60 | 7 or more'
    assert extract_section(html,'Getting enough sleep')=='Needs vary with age.'


def test_reviewed_aerobic_source_is_in_cardio_filter():
    from pathlib import Path
    from src.ingestion import load_documents
    root=Path(__file__).resolve().parents[1]
    doc=next(d for d in load_documents(root/'data'/'sources.json') if d.section=='Aerobic activity - what counts?')
    assert doc.topic=='cardio'
