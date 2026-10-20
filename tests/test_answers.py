import pytest
from pydantic import ValidationError
from src.models import ResearchAnswer
from agents.coordinator import Coordinator


def payload(**changes):
    data = dict(status='answered', answer='General guidance.', key_points=[{'text':'Activity guidance.', 'citations':['c1']}], citations=['c1'], caveats=['Selected adult sources only.'], follow_up_questions=[])
    return data | changes


def test_strict_output_rejects_missing_fields_extra_fields_and_no_evidence():
    with pytest.raises(ValidationError):
        ResearchAnswer.model_validate({'answer':'Looks valid but is missing its structure.'})
    with pytest.raises(ValidationError):
        ResearchAnswer.model_validate(payload(confidence=0.99))
    with pytest.raises(ValidationError):
        ResearchAnswer.model_validate(payload(citations=[]))


class NoModel:
    def generate(self, *args, **kwargs):
        raise AssertionError('A boundary request must never reach the LLM.')


@pytest.mark.parametrize('question,status', [('My knee hurts. Diagnose my injury.','out_of_scope'),('I have chest pain right now.','urgent'),('Tell me which creatine dose to take.','out_of_scope')])
def test_coordinator_refuses_before_retrieval_and_model(question,status):
    result = Coordinator([], NoModel()).research(question, method='vector')
    assert result.answer.status == status
    assert result.model_calls == 0
    assert result.retrieved == []


def test_no_documents_abstains_without_a_model_call():
    result = Coordinator([], NoModel()).research('What is the general activity guidance?',method='keyword')
    assert result.answer.status == 'insufficient_evidence'
    assert result.model_calls == 0
