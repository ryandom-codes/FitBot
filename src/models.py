"""Structured data passed between the pipeline components."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Document(StrictModel):
    source_id: str
    title: str
    url: HttpUrl
    section: str
    text: str = Field(min_length=1)
    topic: str
    evidence_type: str
    published_date: str | None = None
    accessed_date: str
    date_label: str = 'Source date'
    license: str
    scope: str = ''
    limitations: str = ''
    doi: str | None = None
    page: str | None = None


class Chunk(StrictModel):
    id: str
    source_id: str
    title: str
    url: HttpUrl
    section: str
    text: str
    topic: str
    evidence_type: str
    published_date: str | None = None
    accessed_date: str | None = None
    date_label: str = 'Source date'
    page: str | None = None
    scope: str = ''
    limitations: str = ''
    doi: str | None = None


class RetrievedChunk(StrictModel):
    chunk: Chunk
    score: float


class EvidenceQuote(StrictModel):
    citation: str
    field: Literal['text','scope','limitations'] = 'text'
    quote: str = Field(min_length=1,max_length=1200)


class KeyPoint(StrictModel):
    text: str = Field(min_length=1, max_length=1200)
    citations: list[str] = Field(max_length=8)
    supporting_quotes: list[EvidenceQuote] = Field(default_factory=list,max_length=3)


class ResearchAnswer(StrictModel):
    status: Literal['answered', 'insufficient_evidence', 'out_of_scope', 'urgent']
    answer: str = Field(min_length=1, max_length=8000)
    answer_style: Literal['legacy_prose','source_quotes','policy'] = 'legacy_prose'
    key_points: list[KeyPoint] = Field(max_length=6)
    citations: list[str] = Field(max_length=12)
    caveats: list[str] = Field(max_length=6)
    follow_up_questions: list[str] = Field(max_length=3)

    @model_validator(mode='after')
    def answered_requires_evidence(self):
        if self.status == 'answered' and not self.citations:
            raise ValueError('An answered response must cite supplied evidence.')
        return self


class VerificationResult(StrictModel):
    status: Literal['checks_passed', 'flagged', 'policy_response']
    flags: list[str]
    valid_citations: list[str]
    invalid_citations: list[str]
    claim_attachment_coverage: float | None
    semantic_support: Literal['not_reviewed'] = 'not_reviewed'
    quote_integrity: Literal['passed','failed','not_checked'] = 'not_checked'
    checked_quotes: int = 0
    verified_quotes: int = 0


class ResearchResult(StrictModel):
    question: str
    method: str
    answer: ResearchAnswer | None
    retrieved: list[RetrievedChunk]
    verification: VerificationResult | None
    route: str
    error: str | None = None
    response_seconds: float
    model_calls: int = 0
