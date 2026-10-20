"""Exact automatic metrics; semantic completeness/support require review.

Citation occurrence validity is traceability, never entailment or truth.
Key-point attachment is an automatic structural proxy, not claim coverage.
"""

from copy import deepcopy
import hashlib
from pathlib import Path
from time import perf_counter


def _dump(value):
    if value is None:
        return None
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    return value


def retrieval_metrics(retrieved_ids, gold_ids, units):
    """Score the first three returned positions; duplicate IDs count once.

Gold chunks must be fully labeled beforehand. Unit bundles are AND inside
each bundle, OR across alternatives. Empty reference sets are not perfect.
"""
    retrieved, gold = set(retrieved_ids[:3]), set(gold_ids)
    covered = 0
    for unit in units:
        bundles = unit['evidence_bundles']
        if not bundles or any(not bundle for bundle in bundles):
            raise ValueError('Each evidence unit needs nonempty evidence bundles')
        covered += any(set(bundle).issubset(retrieved) for bundle in bundles)
    return {
        'hit_at_3': int(bool(retrieved & gold)) if gold else None,
        'chunk_recall_at_3': len(retrieved & gold) / len(gold) if gold else None,
        'evidence_unit_coverage_at_3': covered / len(units) if units else None,
    }


def citation_metrics(answer, retrieved_ids):
    answer = _dump(answer)
    available = answer is not None
    points = answer.get('key_points', []) if available else []
    occurrences = list(answer.get('citations', [])) if available else []
    for point in points:
        occurrences.extend(point.get('citations', []))
    provided = set(retrieved_ids)
    valid = sum(citation in provided for citation in occurrences)
    attached = sum(bool(point.get('citations')) for point in points)
    return {
        'output_available': int(available),
        'citation_occurrences': len(occurrences),
        'valid_citation_occurrences': valid,
        'invalid_citation_occurrences': len(occurrences) - valid,
        'citation_identity_validity': valid / len(occurrences) if occurrences else None,
        'key_point_count': len(points),
        'attached_key_point_count': attached,
        'key_point_attachment_proxy': attached / len(points) if points else None,
    }


def quote_metrics(verification):
    verification = _dump(verification) or {}
    checked = verification.get('checked_quotes', 0)
    verified = verification.get('verified_quotes', 0)
    return {
        'checked_quotes': checked,
        'verified_quotes': verified,
        'exact_quote_validity': verified / checked if checked else None,
        'quote_integrity': verification.get('quote_integrity', 'not_checked'),
        'verification_flags': '|'.join(verification.get('flags', [])),
    }


def score_review(units_decisions, claims):
    """Score supplied reviewer decisions without inferring them from terms.

Decisions require actual semantic review with retained rationales. Pending
units (fulfilled=None) prevent a complete-answer score. Claim verdicts are
supported, contradicted, not_established, unresolved, relative to supplied
evidence or a disclosed verified computation/frozen boundary policy.
"""
    decisions = [unit['fulfilled'] for unit in units_decisions]
    if any(value is not None and type(value) is not bool for value in decisions):
        raise ValueError('fulfilled must be a boolean or None pending review')
    verdicts = [claim['verdict'] for claim in claims]
    allowed = {'supported', 'contradicted', 'not_established', 'unresolved'}
    if any(verdict not in allowed for verdict in verdicts):
        raise ValueError('Invalid claim verdict')
    fulfilled = sum(value is True for value in decisions)
    pending = sum(value is None for value in decisions)
    unsupported = sum(verdict in {'contradicted', 'not_established'} for verdict in verdicts)
    unresolved = verdicts.count('unresolved')
    adjudicated = len(verdicts) - unresolved
    return {
        'required_units': len(decisions), 'fulfilled_units': fulfilled, 'pending_units': pending,
        'semantic_completeness': fulfilled / len(decisions) if decisions and not pending else None,
        'identified_claims': len(verdicts), 'adjudicated_claims': adjudicated,
        'supported_claims': verdicts.count('supported'),
        'contradicted_claims': verdicts.count('contradicted'),
        'not_established_claims': verdicts.count('not_established'),
        'unresolved_claims': unresolved, 'unsupported_count': unsupported,
        'unsupported_claim_rate': unsupported / adjudicated if adjudicated else None,
        'unsupported_rate_lower_bound': unsupported / len(verdicts) if verdicts else None,
        'unsupported_rate_upper_bound': (unsupported + unresolved) / len(verdicts) if verdicts else None,
    }


def validate_file_hashes(project_root, manifest):
    root = Path(project_root).resolve()
    files = manifest.get('files')
    if not isinstance(files, dict) or not files:
        raise ValueError('Manifest requires frozen file hashes')
    for relative, expected in files.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or path == root:
            raise ValueError('Manifest file is outside the public project')
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Frozen file hash mismatch: {relative}')


def validate_runtime(manifest, client, options, system_prompt):
    if manifest.get('k') != 3 or manifest.get('context_max_words') != 650:
        raise ValueError('Frozen retrieval/context options differ from the paired-evaluation settings')
    if manifest.get('generation_options') != options:
        raise ValueError('Frozen generation options differ')
    if manifest.get('system_prompt_sha256') != hashlib.sha256(system_prompt.encode('utf-8')).hexdigest():
        raise ValueError('Frozen system prompt hash differs')
    if manifest.get('model') != {'name': client.settings.model, 'digest': client.model_digest}:
        raise ValueError('Frozen generation model identity differs')
    if manifest.get('embedding_model') != {'name': client.embedding_model, 'digest': client.embedding_digest}:
        raise ValueError('Frozen embedding model identity differs')


def run_paired(questions, coordinator, on_result=None):
    """One attempt per question/method, alternating order; no silent retries.

Retrieval scores use supplied chunk IDs after shared context packing. The
official answerable category alone contributes eligible retrieval scores.
Policy outputs and errors remain rows; qualitative metrics stay pending.
Optional callback receives snapshots after each attempt for durable storage.
"""
    rows, audit, raw = [], [], []
    for position, question in enumerate(questions):
        methods = ('keyword', 'vector') if position % 2 == 0 else ('vector', 'keyword')
        for method in methods:
            coordinator.client.last_trace = {}
            started = perf_counter()
            try:
                result = coordinator.research(question['question'], method=method,
                                              untrusted_notes=question.get('untrusted_notes', ''))
                answer = _dump(result.answer)
                retrieved = [_dump(item) for item in result.retrieved]
                verification = _dump(result.verification)
                error, route = result.error, result.route
                duration, calls = result.response_seconds, result.model_calls
            except Exception as exc:
                # Unexpected orchestration failures are retained too. Whether a
                # model call began is unknown here, so it must not become zero.
                answer, retrieved, verification = None, [], None
                error, route = f'{type(exc).__name__}: {exc}', 'orchestration_error'
                duration, calls = perf_counter() - started, None
            retrieved_ids = [item['chunk']['id'] for item in retrieved]
            eligible = question['category'] == 'answerable'
            metrics = retrieval_metrics(retrieved_ids, question.get('gold_ids', []) if eligible else [],
                                        question.get('units', []) if eligible else [])
            row = {
                'question_id': question['id'], 'category': question['category'], 'method': method,
                'attempted_outputs': 1, 'model_calls': calls,
                'schema_valid': int(answer is not None),
                'expected_status': question['expected_status'],
                'actual_status': answer['status'] if answer else None,
                'status_match': int(answer is not None and answer['status'] == question['expected_status']),
                'scope_route': route, 'response_seconds': duration,
                'retrieved_count': len(retrieved_ids), 'retrieved_ids': '|'.join(retrieved_ids),
                'verification_status': verification['status'] if verification else None,
                'error': error, **metrics, **citation_metrics(answer, retrieved_ids), **quote_metrics(verification),
                'qualitative_review_status': 'pending', 'semantic_completeness': None,
                'unsupported_count': None, 'unsupported_claim_rate': None,
                'unresolved_claims': None, 'unsupported_rate_lower_bound': None,
                'unsupported_rate_upper_bound': None, 'boundary_compliance': None,
                'injection_resistance': None,
            }
            rows.append(row)
            audit.append({
                'question_record': deepcopy(question),
                'question_id': question['id'], 'category': question['category'], 'method': method,
                'question': question['question'], 'expected_status': question['expected_status'],
                'supplied_evidence': retrieved, 'answer': answer, 'verification': verification,
                'error': error, 'scope_route': route, 'response_seconds': duration,
                'model_calls': calls, 'qualitative_review_status': 'pending',
            })
            raw.append({'question_id': question['id'], 'method': method,
                        'trace': deepcopy(coordinator.client.last_trace), 'error': error,
                        'scope_route': route, 'response_seconds': duration, 'model_calls': calls})
            if on_result:
                on_result(rows, audit, raw)
    return rows, audit, raw
