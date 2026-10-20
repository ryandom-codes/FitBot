from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from src.llm import LocalModelClient
from src.config import load_settings
from src.models import Chunk,RetrievedChunk
from agents.coordinator import Coordinator


class FakeTransport:
    def __init__(self,content='',error=None,reason='stop'):
        self.content,self.error,self.reason,self.calls=content,error,reason,0
    def chat(self,**kwargs):
        self.calls+=1
        assert kwargs['think'] is False
        assert kwargs['stream'] is False
        if self.error: raise self.error
        return SimpleNamespace(message=SimpleNamespace(content=self.content),prompt_eval_count=20,eval_count=12,done_reason=self.reason)


def test_malformed_json_retained_and_not_retried():
    transport=FakeTransport('not json')
    client=LocalModelClient(load_settings(),transport)
    with pytest.raises(ValidationError): client.generate('An evidence question',[])
    assert transport.calls==1
    assert client.last_trace['raw_output']=='not json'


def test_output_limit_is_a_failure_even_if_content_looks_parseable():
    client=LocalModelClient(load_settings(),FakeTransport('{}',reason='length'))
    with pytest.raises(ValueError,match='output limit'): client.generate('Question',[])


def test_timeout_is_preserved_as_failed_attempt():
    client=LocalModelClient(load_settings(),FakeTransport(error=TimeoutError('timed out')))
    chunk=Chunk(id='c',source_id='s',title='Activity',url='https://example.org',section='Guidance',text='Adults perform activity.',topic='exercise',evidence_type='guidance')
    result=Coordinator([chunk],client).research('Adults activity guidance',method='keyword')
    assert result.answer is None
    assert result.model_calls==1
    assert 'TimeoutError' in result.error


def test_boundary_request_does_not_inherit_previous_trace():
    client=LocalModelClient(load_settings(),FakeTransport())
    client.last_trace={'raw_output':'previous answer'}
    Coordinator([],client).research('My knee hurts. Diagnose it.','keyword')
    assert client.last_trace=={}
