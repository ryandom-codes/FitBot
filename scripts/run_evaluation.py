"""Run the frozen paired local-model evaluation with retained private history.

No public report changes occur without --publish. Full local-model traces
remain in the unique private run directory; public audit contains parsed
answers, supplied evidence and frozen question metadata, not full prompts.
"""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import sys
from time import perf_counter

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from src.evaluation import run_paired, validate_file_hashes, validate_runtime

REQUIRED_FROZEN_FILES = {
    'data/sources.json', 'eval/questions.json', 'src/config.py', 'src/ingestion.py',
    'src/models.py', 'src/retrieval.py', 'src/llm.py', 'src/grounding.py', 'src/safety.py',
    'src/evaluation.py', 'scripts/run_evaluation.py', 'agents/coordinator.py',
    'agents/research_agent.py', 'agents/verification_agent.py',
    'scripts/finalize_evaluation.py',
}


def reserve_run(private_dir, run_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', run_id):
        raise ValueError('run-id must be 1..80 simple characters, starting with a letter or number')
    path = Path(private_dir).resolve() / 'evaluation-runs' / run_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir(exist_ok=False)
    return path


def _json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def _csv(path, rows):
    if not rows:
        Path(path).write_text('', encoding='utf-8')
        return
    with Path(path).open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save_artifacts(run_dir, rows, audit, raw, project_root, publish=False):
    """Checkpoint private results; publish only sanitized parsed artifacts."""
    run_dir = Path(run_dir)
    _csv(run_dir / 'evaluation_results.csv', rows)
    _json(run_dir / 'answer_audit.json', audit)
    _json(run_dir / 'raw_outputs.json', raw)
    if publish:
        reports = Path(project_root) / 'reports'
        reports.mkdir(parents=True, exist_ok=True)
        _csv(reports / 'evaluation_results.csv', rows)
        _json(reports / 'answer_audit.json', audit)


def validate_questions(questions, corpus_ids, minimum=15):
    if not isinstance(questions, list) or len(questions) < minimum:
        raise ValueError(f'Evaluation requires at least {minimum} frozen questions')
    ids = set()
    for question in questions:
        for key in ('id', 'category', 'question', 'expected_status', 'gold_ids', 'units'):
            if key not in question:
                raise ValueError(f'Question lacks {key}')
        if not isinstance(question['id'], str) or not question['id'] or question['id'] in ids:
            raise ValueError('Question IDs must be unique nonempty text')
        ids.add(question['id'])
        if question['category'] not in {'answerable', 'missing_evidence', 'boundary', 'injection'}:
            raise ValueError('Invalid question category')
        if question['expected_status'] not in {'answered', 'insufficient_evidence', 'out_of_scope', 'urgent'}:
            raise ValueError('Invalid expected status')
        if not isinstance(question['question'], str) or not question['question'] or len(question['question']) > 2000:
            raise ValueError('Question must be bounded nonempty text')
        notes = question.get('untrusted_notes', '')
        if not isinstance(notes, str) or len(notes) > 1000:
            raise ValueError('Untrusted notes must be bounded text')
        if notes and question['category'] != 'injection':
            raise ValueError('Injection notes must be explicitly categorized')
        if not isinstance(question['gold_ids'], list) or not set(question['gold_ids']).issubset(corpus_ids):
            raise ValueError('Gold evidence IDs must belong to the corpus')
        if not isinstance(question['units'], list):
            raise ValueError('Question units must be a list')
        if question['category'] == 'answerable' and (not question['gold_ids'] or not question['units']):
            raise ValueError('Answerable questions require gold evidence and semantic units')
        for unit in question['units']:
            bundles = unit.get('evidence_bundles', [])
            if question['category'] == 'answerable' and not bundles:
                raise ValueError('Answerable unit needs evidence bundles')
            for bundle in bundles:
                if not isinstance(bundle, list) or not bundle or not set(bundle).issubset(corpus_ids):
                    raise ValueError('Unit evidence bundles must reference the corpus')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True, help='Unique ID; existing private runs cannot be overwritten')
    parser.add_argument('--publish', action='store_true', help='Explicitly update the two public parsed reports')
    args = parser.parse_args()
    from src.config import load_settings
    settings = load_settings(PROJECT)
    try:
        run_dir = reserve_run(settings.private_dir, args.run_id)
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))
    metadata = {
        'run_id': args.run_id, 'started_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'setup', 'publish_requested': args.publish,
        'python_version': platform.python_version(), 'platform': platform.platform(),
        'timing_definition': 'Total coordinator response seconds, including retrieval/generation/verification; no stage timing instrumented.',
        'retrieval_metric_basis': 'Actual supplied chunk IDs after shared k=3 and excerpt text-word budget=650.',
        'citation_metric_definition': 'Occurrences across answer citation list and all key-point citation lists; identity/attachment do not establish support.',
        'qualitative_review': 'pending; no automatic semantic completeness or truth score',
        'attempt_policy': 'one output attempt per question/method; alternate method order; no retries',
    }
    _json(run_dir / 'run_metadata.json', metadata)
    started = perf_counter()
    try:
        manifest_path = PROJECT / 'eval' / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        missing = REQUIRED_FROZEN_FILES - set(manifest.get('files', {}))
        if missing:
            raise ValueError('Manifest must freeze files: ' + ', '.join(sorted(missing)))
        validate_file_hashes(PROJECT, manifest)
        _json(run_dir / 'frozen_manifest.json', manifest)
        metadata['manifest_sha256'] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        from src.ingestion import load_documents, chunk_documents
        from src.llm import LocalModelClient, GENERATION_OPTIONS, SYSTEM_PROMPT
        from src.retrieval import build_index
        from agents.coordinator import Coordinator
        chunks = chunk_documents(load_documents(PROJECT / 'data' / 'sources.json'))
        payload = json.loads((PROJECT / 'eval' / 'questions.json').read_text(encoding='utf-8'))
        questions = payload.get('questions') if isinstance(payload, dict) else payload
        validate_questions(questions, {chunk.id for chunk in chunks})
        client = LocalModelClient(settings)
        validate_runtime(manifest, client, GENERATION_OPTIONS, SYSTEM_PROMPT)
        index = build_index(chunks, client, settings.cache_dir)
        coordinator = Coordinator(chunks, client, index)
        # Setup can take time; reject any concurrent edits before generation.
        validate_file_hashes(PROJECT, manifest)
        metadata.update(status='running', setup_seconds=perf_counter() - started,
                        question_count=len(questions), planned_outputs=2 * len(questions))
        _json(run_dir / 'run_metadata.json', metadata)

        def checkpoint(rows, audit, raw):
            save_artifacts(run_dir, rows, audit, raw, PROJECT, publish=False)
            last = rows[-1]
            print(f"{len(rows)}/{2 * len(questions)} {last['question_id']} {last['method']}: "
                  f"{last['actual_status'] or 'failed'} ({last['response_seconds']:.3f}s)", flush=True)

        rows, audit, raw = run_paired(questions, coordinator, on_result=checkpoint)
        save_artifacts(run_dir, rows, audit, raw, PROJECT, publish=args.publish)
        metadata.update(status='completed', attempted_outputs=len(rows),
                        failed_outputs=sum(row['error'] is not None or not row['schema_valid'] for row in rows),
                        model_calls=sum(row['model_calls'] for row in rows if row['model_calls'] is not None),
                        unknown_model_call_counts=sum(row['model_calls'] is None for row in rows),
                        finished_utc=datetime.now(timezone.utc).isoformat())
        print(f"Retained {len(rows)} attempts in {run_dir}; qualitative review is pending.")
    except BaseException as exc:
        metadata.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                        error=f'{type(exc).__name__}: {exc}', finished_utc=datetime.now(timezone.utc).isoformat())
        raise
    finally:
        _json(run_dir / 'run_metadata.json', metadata)


if __name__ == '__main__':
    main()
