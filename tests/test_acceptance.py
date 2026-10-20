from types import SimpleNamespace
from scripts.run_acceptance import acceptance_row


def result(status='answered',flags=None,calls=1,error=None):
    return SimpleNamespace(answer=SimpleNamespace(status=status),error=error,model_calls=calls,
        response_seconds=1.0,verification=SimpleNamespace(flags=flags or [],verified_quotes=1,checked_quotes=1))


def test_valid_citations_do_not_turn_an_abstention_into_an_answer():
    case=dict(id='a',category='ordinary',question='Question',expected_status='answered')
    assert not acceptance_row(case,result('insufficient_evidence'))['mechanical_pass']
    assert acceptance_row(case,result())['completeness']=='requires_semantic_review'


def test_boundary_pass_requires_no_model_call():
    case=dict(id='b',category='boundary',question='Question',expected_status='out_of_scope')
    assert acceptance_row(case,result('out_of_scope',['personal_prescription'],0))['mechanical_pass']
    assert not acceptance_row(case,result('out_of_scope',['personal_prescription'],1))['mechanical_pass']


def test_error_or_quote_failure_is_retained_as_a_failure():
    case=dict(id='a',category='ordinary',question='Question',expected_status='answered')
    assert not acceptance_row(case,result(flags=['quote_not_in_supplied_evidence']))['mechanical_pass']
    assert not acceptance_row(case,result(error='model unavailable'))['mechanical_pass']
