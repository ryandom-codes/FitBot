"""New development acceptance runs; frozen V2 files/results are never rewritten."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))

from agents.coordinator import Coordinator
from agents.ingestion_agent import ingest
from src.config import load_settings
from src.llm import LocalModelClient,GENERATION_OPTIONS
from src.retrieval import build_index,corpus_fingerprint


def acceptance_row(case,result):
    answer=result.answer
    checks=result.verification
    status=answer.status if answer else 'error'
    flags=checks.flags if checks else []
    boundary=case['category'] in {'boundary','urgent'}
    passed=(not result.error and status==case['expected_status']
        and (boundary or not flags) and (not boundary or result.model_calls==0))
    return dict(id=case['id'],category=case['category'],question=case['question'],
        expected_status=case['expected_status'],actual_status=status,mechanical_pass=passed,
        response_seconds=result.response_seconds,model_calls=result.model_calls,
        verified_quotes=checks.verified_quotes if checks else 0,
        checked_quotes=checks.checked_quotes if checks else 0,
        flags=';'.join(flags),error=result.error or '',
        completeness='requires_semantic_review')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--method',choices=['vector','keyword'],default='vector')
    parser.add_argument('--publish',action='store_true',help='Write parsed results to reports; never raw prompts.')
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',args.run_id):
        parser.error('Use a unique simple run ID, 1..80 characters.')
    settings=load_settings()
    run=settings.private_dir/'acceptance-runs'/args.run_id
    run.mkdir(parents=True,exist_ok=False)
    suite_path=PROJECT/'eval'/'post_v2_acceptance_questions.json'
    suite=json.loads(suite_path.read_text(encoding='utf-8'))
    client=LocalModelClient(settings)
    chunks=ingest(PROJECT/'data'/'sources.json')
    index=build_index(chunks,client,settings.cache_dir) if args.method=='vector' else None
    files=[suite_path,PROJECT/'data'/'sources.json',Path(__file__)]
    files+=list((PROJECT/'src').glob('*.py'))+list((PROJECT/'agents').glob('*.py'))
    manifest=dict(version=suite['version'],started_utc=datetime.now(timezone.utc).isoformat(),
        method=args.method,k=5,context_max_words=650,corpus_fingerprint=corpus_fingerprint(chunks),
        model=dict(name=settings.model,digest=client.model_digest),
        embedding_model=dict(name=settings.embedding_model,digest=client.embedding_digest),
        generation_options=GENERATION_OPTIONS,
        files={p.relative_to(PROJECT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    (run/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    coordinator=Coordinator(chunks,client,index)
    rows=[];audit=[];traces=[]
    for case in suite['questions']:
        result=coordinator.research(case['question'],args.method,untrusted_notes=case.get('untrusted_notes',''))
        rows.append(acceptance_row(case,result))
        audit.append(dict(case=case,result=result.model_dump(mode='json')))
        traces.append(dict(id=case['id'],trace=client.last_trace))
        for filename,value in [('answer_audit.json',audit),('raw_outputs.json',traces)]:
            (run/filename).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        with (run/'acceptance_results.csv').open('w',encoding='utf-8',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]))
            writer.writeheader();writer.writerows(rows)
        print(f"{case['id']}: {rows[-1]['actual_status']}; checks={rows[-1]['mechanical_pass']}; {result.response_seconds:.2f}s",flush=True)
    if args.publish:
        # Parsed application answers/evidence are reviewable; model input traces stay private.
        for filename in ['acceptance_results.csv','answer_audit.json']:
            target=PROJECT/'reports'/('post_v2_'+filename)
            if target.exists():raise FileExistsError(f'Refusing to overwrite {target}')
            target.write_bytes((run/filename).read_bytes())
    print(f"Mechanical/status acceptance: {sum(row['mechanical_pass'] for row in rows)}/{len(rows)}. Completeness still needs semantic review. Private run: {run}")
    return 0 if all(row['mechanical_pass'] for row in rows) else 1


if __name__=='__main__':
    raise SystemExit(main())
