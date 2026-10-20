import pytest
from scripts.finalize_evaluation import merge_reviews


def fixture():
    q={'category':'answerable','units':[{'id':'u','meaning':'A meaning'}]}
    audit=[{'question_id':'Q01','method':'keyword','question_record':q,'answer':{'answer':'A claim'}}]
    rows=[{'question_id':'Q01','method':'keyword'}]
    mapping={'blind':{'question_id':'Q01','method':'keyword'}}
    review={'review_id':'blind','unit_decisions':[{'unit_id':'u','fulfilled':True,'rationale':'Meaning conveyed','response_span':'A claim'}],
            'claims':[{'span':'A claim','citations':['c'],'verdict':'not_established','rationale':'Missing support','evidence_excerpt':'Not present','citation_entailments':[{'citation':'c','entails':False,'rationale':'Unrelated'}]}],
            'behavior_compliant':None,'behavior_rationale':None}
    return rows,audit,mapping,review


def test_merges_actual_semantic_decisions_without_keyword_scoring():
    rows,audit,mapping,review=fixture()
    result=merge_reviews(rows,audit,mapping,[review])
    assert result[0]['semantic_completeness']==1
    assert result[0]['unsupported_count']==1
    assert result[0]['citation_entailment_rate']==0


def test_missing_or_duplicated_reviews_cannot_be_reported_complete():
    rows,audit,mapping,review=fixture()
    with pytest.raises(ValueError): merge_reviews(rows,audit,mapping,[])
    with pytest.raises(ValueError): merge_reviews(rows,audit,mapping,[review,review])


def test_frozen_units_must_all_receive_decisions():
    rows,audit,mapping,review=fixture()
    review['unit_decisions']=[]
    with pytest.raises(ValueError,match='unit'): merge_reviews(rows,audit,mapping,[review])
