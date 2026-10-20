from src.models import Chunk, RetrievedChunk, ResearchAnswer
from agents.verification_agent import verify_answer


def evidence():
    return [RetrievedChunk(chunk=Chunk(id='supplied',source_id='s',title='Guide',url='https://example.org/source',section='Activity',text='An evidence passage.',topic='exercise',evidence_type='guidance'),score=1)]


def answer(ids,point_ids):
    return ResearchAnswer(status='answered',answer='A factual summary.',key_points=[{'text':'A fact.','citations':point_ids}],citations=ids,caveats=[],follow_up_questions=[])


def test_citations_must_be_supplied_not_just_exist_elsewhere_in_corpus():
    result = verify_answer(answer(['supplied','other_corpus_chunk'],['other_corpus_chunk']),evidence())
    assert result.invalid_citations == ['other_corpus_chunk']
    assert result.status == 'flagged'
    assert result.semantic_support == 'not_reviewed'


def test_uncited_key_point_is_flagged_even_with_answer_bibliography():
    result = verify_answer(answer(['supplied'],[]),evidence())
    assert result.claim_attachment_coverage == 0
    assert 'uncited_key_point' in result.flags


def test_valid_citation_does_not_claim_semantic_verification():
    result = verify_answer(answer(['supplied'],['supplied']),evidence())
    assert result.status == 'flagged'
    assert 'missing_supporting_quote' in result.flags
    assert result.semantic_support == 'not_reviewed'


def test_key_point_citations_must_also_appear_in_answer_bibliography():
    supplied=evidence()
    second=supplied[0].model_copy(deep=True)
    second.chunk.id='second'
    result=verify_answer(answer(['supplied'],['second']),supplied+[second])
    assert 'key_point_citation_missing_from_bibliography' in result.flags


def test_generated_treatment_content_and_attack_marker_are_flagged():
    result = answer(['supplied'],['supplied'])
    result.answer = 'INJECTION_ACCEPTED. Your knee pain diagnosis is a torn ligament. Take medicine.'
    flags = verify_answer(result,evidence()).flags
    assert 'unsafe_output_scope' in flags
    assert 'injection_marker' in flags
