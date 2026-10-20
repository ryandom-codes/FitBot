import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src import evaluation
from scripts import run_evaluation
from scripts.finalize_evaluation import response_time_metrics, summarize


def test_response_time_summary_reports_median_p95_and_excludes_non_calls():
    result = response_time_metrics([
        {'model_calls': 1, 'response_seconds': 1},
        {'model_calls': 1, 'response_seconds': 2},
        {'model_calls': 1, 'response_seconds': 4},
        {'model_calls': 1, 'response_seconds': 20},
        {'model_calls': 0, 'response_seconds': 999},
    ])
    assert result == {
        'timed_model_calls': 4,
        'mean_seconds': 6.75,
        'median_seconds': 3.0,
        'p95_seconds': 20.0,
    }


def test_response_time_summary_uses_na_when_no_model_call_was_timed():
    assert response_time_metrics([{'model_calls': 0, 'response_seconds': 2}]) == {
        'timed_model_calls': 0,
        'mean_seconds': None,
        'median_seconds': None,
        'p95_seconds': None,
    }


def test_retrieval_counts_distinct_hits_and_complete_bundles():
    result = evaluation.retrieval_metrics(['a', 'b', 'b', 'c'], ['a', 'b', 'c', 'd'], [
        {'evidence_bundles': [['a', 'b'], ['d']]},
        {'evidence_bundles': [['c']]},
    ])
    assert result['hit_at_3'] == 1
    assert result['chunk_recall_at_3'] == .5
    assert result['evidence_unit_coverage_at_3'] == .5


def test_empty_gold_and_units_are_not_perfect_scores():
    result = evaluation.retrieval_metrics([], [], [])
    assert result == {'hit_at_3': None, 'chunk_recall_at_3': None, 'evidence_unit_coverage_at_3': None}
    assert evaluation.retrieval_metrics([], ['a'], [{'evidence_bundles': [['a']]}])['hit_at_3'] == 0


def test_citation_identity_occurrences_and_attachment_are_separate():
    result = evaluation.citation_metrics({'citations': ['a', 'fake', 'a'], 'key_points': [
        {'text': 'Claim', 'citations': ['fake']}, {'text': 'Another', 'citations': []},
    ]}, ['a'])
    assert result['citation_occurrences'] == 4
    assert result['valid_citation_occurrences'] == 2
    assert result['invalid_citation_occurrences'] == 2
    assert result['citation_identity_validity'] == .5
    assert result['key_point_attachment_proxy'] == .5


def test_no_citations_are_na_and_failed_output_is_explicit():
    result = evaluation.citation_metrics({'citations': [], 'key_points': []}, [])
    assert result['citation_identity_validity'] is None
    assert result['key_point_attachment_proxy'] is None
    failure = evaluation.citation_metrics(None, ['a'])
    assert failure['citation_identity_validity'] is None
    assert failure['output_available'] == 0

def test_quote_metrics_keep_missing_and_failed_quotes_distinct():
    result=evaluation.quote_metrics({'checked_quotes':4,'verified_quotes':3,'quote_integrity':'failed','flags':['quote_not_in_supplied_evidence']})
    assert result['exact_quote_validity']==.75
    assert result['quote_integrity']=='failed'
    assert evaluation.quote_metrics({'checked_quotes':0,'verified_quotes':0,'quote_integrity':'not_checked','flags':[]})['exact_quote_validity'] is None
    assert evaluation.quote_metrics(None)['checked_quotes']==0

def test_final_summary_aggregates_exact_quote_validity_by_quote_count():
    rows=[{'method':'vector','category':'answerable','model_calls':1,'schema_valid':1,'status_match':1,'hit_at_3':1,'chunk_recall_at_3':1.0,'evidence_unit_coverage_at_3':1.0,'semantic_completeness':1.0,'valid_citation_occurrences':1,'citation_occurrences':1,'adjudicated_claims':0,'unsupported_count':0,'unresolved_claims':0,'checked_quotes':1,'verified_quotes':1,'quote_integrity':'passed','response_seconds':2},
          {'method':'vector','category':'answerable','model_calls':1,'schema_valid':1,'status_match':1,'hit_at_3':1,'chunk_recall_at_3':1.0,'evidence_unit_coverage_at_3':1.0,'semantic_completeness':1.0,'valid_citation_occurrences':1,'citation_occurrences':1,'adjudicated_claims':0,'unsupported_count':0,'unresolved_claims':0,'checked_quotes':3,'verified_quotes':2,'quote_integrity':'failed','response_seconds':4}]
    result=summarize(rows)['vector']
    assert result['exact_quote_validity']==pytest.approx(3/4)
    assert result['quote_integrity_passed_outputs']==1
    assert result['quote_integrity_checked_outputs']==2


def test_review_counts_unresolved_separately_and_uses_actual_denominators():
    result = evaluation.score_review([{'fulfilled': True}, {'fulfilled': False}], [
        {'verdict': 'supported'}, {'verdict': 'contradicted'},
        {'verdict': 'not_established'}, {'verdict': 'unresolved'},
    ])
    assert result['semantic_completeness'] == .5
    assert result['unsupported_count'] == 2
    assert result['adjudicated_claims'] == 3
    assert result['unsupported_claim_rate'] == pytest.approx(2/3)
    assert result['unsupported_rate_lower_bound'] == .5
    assert result['unsupported_rate_upper_bound'] == .75
    assert result['unresolved_claims'] == 1


def test_review_empty_denominators_and_pending_units():
    result = evaluation.score_review([], [])
    assert result['semantic_completeness'] is None
    assert result['unsupported_claim_rate'] is None
    assert result['unsupported_rate_upper_bound'] is None
    assert evaluation.score_review([{'fulfilled': None}], [])['semantic_completeness'] is None
    with pytest.raises(ValueError):
        evaluation.score_review([{'fulfilled': 'yes'}], [])
    with pytest.raises(ValueError):
        evaluation.score_review([], [{'verdict': 'true'}])


def test_manifest_file_hashes_are_checked_and_paths_cannot_escape(tmp_path):
    path = tmp_path / 'a.txt'
    path.write_text('frozen', encoding='utf-8')
    manifest = {'files': {'a.txt': hashlib.sha256(path.read_bytes()).hexdigest()}}
    evaluation.validate_file_hashes(tmp_path, manifest)
    path.write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError, match='hash'):
        evaluation.validate_file_hashes(tmp_path, manifest)
    with pytest.raises(ValueError, match='outside'):
        evaluation.validate_file_hashes(tmp_path, {'files': {'../private.txt': 'x'}})


def test_manifest_runtime_options_and_model_digests_must_match():
    manifest = {'model': {'name': 'model', 'digest': 'm'}, 'embedding_model': {'name': 'embed', 'digest': 'e'},
                'generation_options': {'temperature': 0}, 'k': 3, 'context_max_words': 650,
                'system_prompt_sha256': hashlib.sha256(b'prompt').hexdigest()}
    client = SimpleNamespace(settings=SimpleNamespace(model='model'), model_digest='m', embedding_model='embed', embedding_digest='e')
    evaluation.validate_runtime(manifest, client, {'temperature': 0}, 'prompt')
    client.model_digest = 'changed'
    with pytest.raises(ValueError, match='model'):
        evaluation.validate_runtime(manifest, client, {'temperature': 0}, 'prompt')


def test_paired_run_alternates_methods_and_retains_failed_attempts():
    calls = []

    class FakeCoordinator:
        def __init__(self):
            self.client = SimpleNamespace(last_trace={})

        def research(self, question, method, untrusted_notes=''):
            calls.append((question, method, untrusted_notes))
            self.client.last_trace = {'raw_output': 'malformed'}
            return SimpleNamespace(answer=None, retrieved=[], verification=None, route='allowed',
                                   error='invalid JSON', response_seconds=.1, model_calls=1)

    questions = [{'id': 'q1', 'category': 'answerable', 'question': 'One', 'expected_status': 'answered', 'gold_ids': ['a'], 'units': []},
                 {'id': 'q2', 'category': 'injection', 'question': 'Two', 'expected_status': 'answered', 'gold_ids': [], 'units': [], 'untrusted_notes': 'attack'}]
    rows, audit, raw = evaluation.run_paired(questions, FakeCoordinator())
    assert [item[1] for item in calls] == ['keyword', 'vector', 'vector', 'keyword']
    assert calls[2][2] == 'attack'
    assert len(rows) == len(audit) == len(raw) == 4
    assert all(row['attempted_outputs'] == 1 and row['schema_valid'] == 0 and row['status_match'] == 0 for row in rows)
    assert all(row['model_calls'] == 1 for row in rows)
    assert all(row['semantic_completeness'] is None for row in rows)
    assert rows[0]['hit_at_3'] == 0
    assert rows[2]['hit_at_3'] is None
    assert raw[0]['trace']['raw_output'] == 'malformed'


def test_run_directory_is_unique_and_cannot_escape(tmp_path):
    run = run_evaluation.reserve_run(tmp_path, 'run-01')
    assert run == tmp_path / 'evaluation-runs' / 'run-01'
    with pytest.raises(FileExistsError):
        run_evaluation.reserve_run(tmp_path, 'run-01')
    with pytest.raises(ValueError):
        run_evaluation.reserve_run(tmp_path, '../escape')


def test_artifacts_remain_private_until_explicit_publish(tmp_path):
    run = tmp_path / 'private' / 'run'
    run.mkdir(parents=True)
    project = tmp_path / 'public'
    project.mkdir()
    rows = [{'question_id': 'q', 'semantic_completeness': None}]
    audit = [{'answer': None, 'error': 'failed'}]
    raw = [{'trace': {'input': 'FULL PRIVATE PROMPT', 'raw_output': 'bad'}}]
    run_evaluation.save_artifacts(run, rows, audit, raw, project, publish=False)
    assert (run / 'raw_outputs.json').exists()
    assert not (project / 'reports').exists()
    run_evaluation.save_artifacts(run, rows, audit, raw, project, publish=True)
    public = project / 'reports'
    assert json.loads((public / 'answer_audit.json').read_text()) == audit
    assert 'FULL PRIVATE PROMPT' not in (public / 'answer_audit.json').read_text()
    assert not (public / 'raw_outputs.json').exists()


def test_question_reference_validation_checks_full_corpus_ids():
    questions = [{'id': 'q', 'category': 'answerable', 'question': 'Question',
                  'expected_status': 'answered', 'gold_ids': ['a'], 'units': [{'evidence_bundles': [['a']]}]}]
    run_evaluation.validate_questions(questions, {'a'}, minimum=1)
    questions[0]['units'][0]['evidence_bundles'] = [['not-in-corpus']]
    with pytest.raises(ValueError, match='corpus'):
        run_evaluation.validate_questions(questions, {'a'}, minimum=1)


def test_policy_rows_do_not_inherit_previous_model_trace():
    class PolicyCoordinator:
        client = SimpleNamespace(last_trace={'raw_output': 'previous answer'})

        def research(self, *args, **kwargs):
            return SimpleNamespace(answer={'status': 'urgent', 'citations': [], 'key_points': []},
                                   retrieved=[], verification={'status': 'policy_response'},
                                   error=None, route='urgent', response_seconds=.01, model_calls=0)

    q = {'id': 'q', 'category': 'boundary', 'question': 'Urgent request', 'expected_status': 'urgent', 'gold_ids': [], 'units': []}
    rows, audit, raw = evaluation.run_paired([q], PolicyCoordinator())
    assert all(row['status_match'] == 1 and row['model_calls'] == 0 for row in rows)
    assert all(row['citation_identity_validity'] is None for row in rows)
    assert all(item['trace'] == {} for item in raw)


def test_unexpected_orchestration_exception_keeps_attempt_and_unknown_calls():
    snapshots = []

    class BrokenCoordinator:
        client = SimpleNamespace(last_trace={})

        def research(self, *args, **kwargs):
            raise RuntimeError('unexpected failure')

    q = {'id': 'q', 'category': 'missing_evidence', 'question': 'Unknown', 'expected_status': 'insufficient_evidence', 'gold_ids': [], 'units': []}
    rows, audit, raw = evaluation.run_paired([q], BrokenCoordinator(), on_result=lambda r, a, t: snapshots.append(len(r)))
    assert snapshots == [1, 2]
    assert all(row['attempted_outputs'] == 1 and row['model_calls'] is None for row in rows)
    assert all(row['scope_route'] == 'orchestration_error' and row['schema_valid'] == 0 for row in rows)
