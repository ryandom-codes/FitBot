import json
from types import SimpleNamespace
import pytest
from src.config import load_settings
from src.models import Chunk,RetrievedChunk,ResearchAnswer
from src.llm import LocalModelClient
from agents.verification_agent import verify_answer

def supplied():
    return [RetrievedChunk(chunk=Chunk(id='long-hash-source',source_id='guide',title='Guide',url='https://example.org',section='Serving',text='One serving contains 280 calories. Two servings contain 560 calories.',topic='nutrition',evidence_type='guidance',scope='General adult education.',limitations='Not a personal prescription.'),score=1)]

class SelectingTransport:
    def __init__(self,payload):self.payload=payload;self.request=None
    def chat(self,**kwargs):
        self.request=kwargs
        return SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.payload)),prompt_eval_count=10,eval_count=10,done_reason='stop')

def test_model_selection_resolves_exact_text_and_id_without_generated_facts():
    transport=SelectingTransport({'selected_spans':['E1S2'],'status':'answered'})
    client=LocalModelClient(load_settings(),transport)
    answer=client.generate('How many calories in two servings?',supplied())
    assert answer.key_points[0].text=='Two servings contain 560 calories.'
    assert answer.key_points[0].citations==['long-hash-source']
    assert answer.key_points[0].supporting_quotes[0].quote==answer.key_points[0].text
    assert answer.answer_style=='source_quotes'
    assert 'personal prescription' in ' '.join(answer.caveats)
    schema=transport.request['format']
    assert 'E1S2' in schema['properties']['selected_spans']['items']['enum']
    assert 'long-hash-source' not in json.dumps(schema)
    assert 'response_schema' in transport.request['messages'][1]['content']

@pytest.mark.parametrize('payload',[
 {'selected_spans':['FAKE_CHUNK_999'],'status':'answered'},
 {'selected_spans':[],'status':'answered'},
 {'selected_spans':['E1S1'],'status':'insufficient_evidence'},
 {'selected_spans':['E1S1'],'status':'answered','answer':'Invented prose'},
])
def test_bad_or_inconsistent_selections_are_retained_as_failures(payload):
    client=LocalModelClient(load_settings(),SelectingTransport(payload))
    with pytest.raises(ValueError):client.generate('Serving question',supplied())
    assert client.last_trace['raw_output'] is not None

def quoted_answer():
    return ResearchAnswer.model_validate({'status':'answered','answer_style':'source_quotes','answer':'The retrieved sources state:\n\nTwo servings contain 560 calories.','key_points':[{'text':'Two servings contain 560 calories.','citations':['long-hash-source'],'supporting_quotes':[{'citation':'long-hash-source','field':'text','quote':'Two servings contain 560 calories.'}]}],'citations':['long-hash-source'],'caveats':[],'follow_up_questions':[]})

def test_quote_check_flags_changed_number_even_with_valid_id():
    answer=quoted_answer()
    answer.key_points[0].supporting_quotes[0].quote='Two servings contain 500 calories.'
    checked=verify_answer(answer,supplied())
    assert 'quote_not_in_supplied_evidence' in checked.flags
    assert checked.quote_integrity=='failed'

def test_quote_presence_does_not_validate_a_different_claim():
    answer=quoted_answer()
    answer.key_points[0].text='Two servings cure disease.'
    checked=verify_answer(answer,supplied())
    assert 'point_differs_from_verified_quote' in checked.flags

def test_quote_mode_rejects_uncited_narrative_and_generated_caveats():
    answer=quoted_answer()
    answer.answer='These calories will cause weight loss.'
    answer.caveats=['This source proves all people will benefit.']
    checked=verify_answer(answer,supplied())
    assert 'answer_differs_from_quoted_points' in checked.flags
    assert 'caveat_not_from_source_metadata' in checked.flags

def test_real_quote_integrity_does_not_claim_semantic_truth():
    answer=quoted_answer()
    checked=verify_answer(answer,supplied())
    assert checked.quote_integrity=='passed'
    assert checked.verified_quotes==1
    assert checked.semantic_support=='not_reviewed'

def test_missing_quote_is_flagged_for_legacy_generated_points():
    answer=ResearchAnswer(status='answered',answer='Some fact.',key_points=[{'text':'Some fact.','citations':['long-hash-source']}],citations=['long-hash-source'],caveats=[],follow_up_questions=[])
    assert 'missing_supporting_quote' in verify_answer(answer,supplied()).flags

def test_repeated_source_sentences_do_not_make_repeated_answer_points():
    transport=SelectingTransport({'selected_spans':['E1S1','E1S2'],'status':'answered'})
    evidence=supplied()
    evidence[0].chunk.text='One serving contains 280 calories. One serving contains 280 calories.'
    answer=LocalModelClient(load_settings(),transport).generate('How many calories in one serving?',evidence)
    assert len(answer.key_points)==1

def test_decoding_schema_constrains_abstention_to_no_selected_evidence():
    from src.grounding import make_spans,selection_schema
    schema=selection_schema(make_spans(supplied()))
    branches={b['properties']['status']['const']:b for b in schema['oneOf']}
    assert branches['answered']['properties']['selected_spans']['minItems']==1
    assert branches['insufficient_evidence']['properties']['selected_spans']['maxItems']==0

def test_source_list_lines_remain_separate_exact_quotes():
    from src.grounding import make_spans
    evidence=supplied()
    evidence[0].chunk.text='Examples include:\n\nWalking fast\n\nWater aerobics\n\nRiding a bike.'
    spans=make_spans(evidence)
    assert [span.text for span in spans if span.field=='text']==['Examples include:','Walking fast','Water aerobics','Riding a bike.']

def test_repeated_rule_with_leading_conjunction_keeps_clean_standalone_quote():
    transport=SelectingTransport({'status':'answered','selected_spans':['E1S1','E1S2']})
    evidence=supplied()
    evidence[0].chunk.text='AND adults need two days of strengthening. Adults need two days of strengthening.'
    answer=LocalModelClient(load_settings(),transport).generate('How often?',evidence)
    assert len(answer.key_points)==1
    assert answer.key_points[0].text=='Adults need two days of strengthening.'


def test_abstention_offers_a_narrower_question_about_supplied_source():
    client=LocalModelClient(load_settings(),SelectingTransport({'status':'insufficient_evidence','selected_spans':[]}))
    answer=client.generate('Which diet will guarantee my best results?',supplied())
    assert answer.status=='insufficient_evidence'
    assert answer.citations==[]
    assert answer.follow_up_questions==['What does "Guide" say in the "Serving" section?']
    assert verify_answer(answer,supplied()).flags==[]
