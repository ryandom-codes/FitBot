"""Scope -> retrieval -> generation -> mechanical checks, with explicit failures."""
from time import perf_counter
from src.models import ResearchAnswer, ResearchResult, VerificationResult
from src.safety import classify_request
from agents.research_agent import answer_question
from agents.verification_agent import verify_answer


class Coordinator:
    def __init__(self, chunks, client, index=None):
        self.chunks, self.client, self.index = chunks, client, index

    def research(self, question, method='vector', topic=None, personal_summary=None, untrusted_notes=''):
        if method not in {'keyword','vector'}:
            raise ValueError('Choose keyword or vector retrieval.')
        start = perf_counter()
        if hasattr(self.client, 'last_trace'):
            self.client.last_trace = {}
        decision = classify_request(question)
        retrieved, answer, verification, error, calls = [], None, None, None, 0
        try:
            if decision.route != 'allowed':
                answer = ResearchAnswer(status=decision.route, answer=decision.response, key_points=[],citations=[],
                    caveats=['A fixed scope response, not medical assessment.'],follow_up_questions=[])
                verification = VerificationResult(status='policy_response',flags=[decision.reason],valid_citations=[],invalid_citations=[],claim_attachment_coverage=None)
            elif not self.chunks:
                answer = ResearchAnswer(status='insufficient_evidence',answer='No reviewed evidence is available for this question.',key_points=[],citations=[],caveats=['Load the reviewed source collection first.'],follow_up_questions=[])
                verification = verify_answer(answer,[])
            else:
                from src.retrieval import keyword_search, vector_search, prepare_evidence
                ranked = keyword_search(question,self.chunks,k=5,topic=topic) if method == 'keyword' else vector_search(question,self.index,self.client,k=5,topic=topic)
                retrieved = prepare_evidence(ranked,max_words=650)
                if not retrieved:
                    answer = ResearchAnswer(status='insufficient_evidence',answer='No evidence was retrieved in the selected collection.',key_points=[],citations=[],caveats=['Try a broader collection.'],follow_up_questions=[])
                else:
                    calls = 1
                    answer = answer_question(self.client, question, retrieved, personal_summary, untrusted_notes)
                verification = verify_answer(answer,retrieved)
        except Exception as exc:
            # Retain failures instead of making up a fallback answer or silently retrying.
            error = f'{type(exc).__name__}: {exc}'
        return ResearchResult(question=question,method=method,answer=answer,retrieved=retrieved,
            verification=verification,route=decision.route,error=error,response_seconds=round(perf_counter()-start,3),model_calls=calls)
