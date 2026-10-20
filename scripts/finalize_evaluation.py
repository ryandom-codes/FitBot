"""Merge explicit semantic review judgments; never generate or infer judgments."""
import argparse
from copy import deepcopy
import csv
import json
import math
from statistics import mean, median
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from src.evaluation import score_review,validate_file_hashes


def merge_reviews(rows,audit,mapping,reviews):
    keyed={}
    for review in reviews:
        code=review['review_id']
        if code not in mapping: raise ValueError('Unknown blinded review ID')
        identity=(mapping[code]['question_id'],mapping[code]['method'])
        if identity in keyed: raise ValueError('Duplicate review')
        keyed[identity]=review
    expected={(row['question_id'],row['method']) for row in rows}
    if set(keyed)!=expected: raise ValueError('Every attempted response must have one explicit review')
    records={(row['question_id'],row['method']):row for row in audit}
    if set(records)!=expected: raise ValueError('Audit and CSV identities differ')
    result=[]
    for row in rows:
        identity=(row['question_id'],row['method'])
        review=keyed[identity]; question=records[identity]['question_record']
        expected_units=[unit['id'] for unit in question['units']]
        decisions=review['unit_decisions']
        if sorted(d['unit_id'] for d in decisions)!=sorted(expected_units):
            raise ValueError('Reviewed unit IDs must match all frozen units exactly')
        for decision in decisions:
            if type(decision['fulfilled']) is not bool or not decision.get('rationale'):
                raise ValueError('Each unit needs a boolean and rationale')
        claims=review['claims']
        for claim in claims:
            if not claim.get('span') or not claim.get('rationale'):
                raise ValueError('Each claim needs a response span and evidence rationale')
        scored=score_review(decisions,claims)
        links=[link for claim in claims for link in claim.get('citation_entailments',[])]
        if any(type(link['entails']) is not bool for link in links):
            raise ValueError('Citation entailment must be explicitly judged')
        behavioral=review.get('behavior_compliant')
        if question['category'] in {'boundary','injection','missing_evidence'} and type(behavioral) is not bool:
            raise ValueError('Behavioral cases require explicit compliance review')
        updated=deepcopy(row)
        updated.update(scored,qualitative_review_status='AI-assisted reviewed',
            reviewed_claim_count=len(claims),attached_claim_count=sum(bool(c['citations']) for c in claims),
            citation_attachment_coverage=sum(bool(c['citations']) for c in claims)/len(claims) if claims else None,
            citation_entailment_count=sum(link['entails'] for link in links),
            reviewed_citation_associations=len(links),citation_entailment_rate=sum(link['entails'] for link in links)/len(links) if links else None,
            boundary_compliance=int(behavioral) if question['category']=='boundary' else None,
            injection_resistance=int(behavioral) if question['category']=='injection' else None,
            missing_evidence_behavior=int(behavioral) if question['category']=='missing_evidence' else None)
        result.append(updated)
    return result


def _mean(rows,key):
    values=[float(r[key]) for r in rows if r.get(key) not in {None,''}]
    return sum(values)/len(values) if values else None


def response_time_metrics(rows):
    """Summarize observed model-call durations; p95 uses nearest rank."""
    values=sorted(float(r['response_seconds']) for r in rows
                  if int(r.get('model_calls') or 0)>0 and r.get('response_seconds') not in {None,''})
    if not values:
        return {'timed_model_calls':0,'mean_seconds':None,'median_seconds':None,'p95_seconds':None}
    p95_index=max(0,math.ceil(0.95*len(values))-1)
    return {'timed_model_calls':len(values),'mean_seconds':mean(values),
            'median_seconds':median(values),'p95_seconds':values[p95_index]}


def summarize(rows):
    summary={}
    for method in ['keyword','vector']:
        group=[r for r in rows if r['method']==method]
        ordinary=[r for r in group if r['category']=='answerable']
        calls=[r for r in group if int(r['model_calls'] or 0)>0]
        valid=sum(int(r['valid_citation_occurrences']) for r in group)
        cited=sum(int(r['citation_occurrences']) for r in group)
        claims=sum(int(r['adjudicated_claims']) for r in group)
        unsupported=sum(int(r['unsupported_count']) for r in group)
        checked_quotes=sum(int(r.get('checked_quotes') or 0) for r in group)
        valid_quotes=sum(int(r.get('verified_quotes') or 0) for r in group)
        checked_outputs=[r for r in group if int(r.get('checked_quotes') or 0)>0]
        summary[method]={'attempted_outputs':len(group),'model_calls':len(calls),
          'schema_valid_outputs':sum(int(r['schema_valid']) for r in group),
          'status_matches':sum(int(r['status_match']) for r in group),
          'answerable_questions':len(ordinary),'hit_at_3':_mean(ordinary,'hit_at_3'),
          'chunk_recall_at_3':_mean(ordinary,'chunk_recall_at_3'),
          'evidence_unit_coverage_at_3':_mean(ordinary,'evidence_unit_coverage_at_3'),
          'semantic_completeness':_mean(ordinary,'semantic_completeness'),
          'citation_identity_validity':valid/cited if cited else None,
          'valid_citation_occurrences':valid,'citation_occurrences':cited,
          'unsupported_count':unsupported,'adjudicated_claims':claims,
          'unsupported_claim_rate':unsupported/claims if claims else None,
          'unresolved_claims':sum(int(r['unresolved_claims']) for r in group),
          'exact_quote_validity':valid_quotes/checked_quotes if checked_quotes else None,
          'exact_quotes_verified':valid_quotes,'exact_quotes_checked':checked_quotes,
          'quote_integrity_passed_outputs':sum(r.get('quote_integrity')=='passed' for r in checked_outputs),
          'quote_integrity_checked_outputs':len(checked_outputs),
          'response_time':response_time_metrics(group)}
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--mapping',type=Path,required=True)
    parser.add_argument('--reviews',type=Path,required=True)
    args=parser.parse_args()
    from src.config import load_settings
    settings=load_settings(PROJECT)
    run=(settings.private_dir/'evaluation-runs'/args.run_id).resolve()
    if run.parent != (settings.private_dir/'evaluation-runs').resolve(): parser.error('Run must stay in evaluation-runs')
    metadata=json.loads((run/'run_metadata.json').read_text(encoding='utf-8'))
    if metadata['status']!='completed': parser.error('Only completed runs can be finalized')
    manifest=json.loads((run/'frozen_manifest.json').read_text(encoding='utf-8'))
    validate_file_hashes(PROJECT,manifest)
    with (run/'evaluation_results.csv').open(encoding='utf-8',newline='') as handle: rows=list(csv.DictReader(handle))
    audit=json.loads((run/'answer_audit.json').read_text(encoding='utf-8'))
    mapping=json.loads(args.mapping.read_text(encoding='utf-8'))
    review_payload=json.loads(args.reviews.read_text(encoding='utf-8'))
    reviews=review_payload['reviews']
    final=merge_reviews(rows,audit,mapping,reviews)
    for row in final:
        if row['error']=='': row['error']=None
    reports=PROJECT/'reports'; reports.mkdir(exist_ok=True)
    with (reports/'evaluation_results.csv').open('w',encoding='utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(final[0])); writer.writeheader(); writer.writerows(final)
    enriched=[]
    keyed={(mapping[r['review_id']]['question_id'],mapping[r['review_id']]['method']):r for r in reviews}
    for record in audit:
        reviewed=deepcopy(record)
        reviewed['qualitative_review_status']='AI-assisted reviewed'
        reviewed['semantic_review']=keyed[(record['question_id'],record['method'])]
        enriched.append(reviewed)
    for name,value in [('answer_audit.json',enriched),('qualitative_review.json',review_payload),('evaluation_summary.json',summarize(final))]:
        (reports/name).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    # Preserve the first automatic outputs; reviewed versions are additional artifacts.
    (run/'adjudicated_review.json').write_text(json.dumps(review_payload,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (run/'reviewed_evaluation_results.csv').write_bytes((reports/'evaluation_results.csv').read_bytes())
    print(json.dumps(summarize(final),indent=2))


if __name__=='__main__': main()
