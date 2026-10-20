"""Resolve model-selected spans without letting it rewrite evidence or citations."""
from dataclasses import dataclass
from copy import deepcopy
import re
from typing import Literal
from pydantic import Field
from src.models import StrictModel,ResearchAnswer,KeyPoint,EvidenceQuote


class EvidenceSelection(StrictModel):
    selected_spans: list[str] = Field(max_length=6)
    status: Literal['answered','insufficient_evidence']


@dataclass(frozen=True)
class EvidenceSpan:
    alias: str
    citation: str
    field: str
    text: str


def make_spans(evidence):
    spans=[]
    for position,item in enumerate(evidence,1):
        number=0
        for field in ['text','scope','limitations']:
            # Keep whole sentences, including numbers and qualifications. This
            # is a formatting split, not a claim that a sentence is independent.
            lines=getattr(item.chunk,field).splitlines()
            for line in lines:
                for sentence in re.split(r'(?<=[.!?])\s+(?=[A-Z“"(])',line):
                    text=' '.join(sentence.split())
                    if not text:continue
                    if len(text)>1200:
                        raise ValueError('A source span exceeds the bounded quote size.')
                    number+=1
                    spans.append(EvidenceSpan(f'E{position}S{number}',item.chunk.id,field,text))
    return spans


def selection_schema(spans):
    schema=EvidenceSelection.model_json_schema()
    schema['properties']['selected_spans']['items']['enum']=[s.alias for s in spans]
    # Decode the status first, then enforce its compatible selection shape.
    # Runtime validation still rejects malformed provider responses.
    schema['properties']={key:schema['properties'][key] for key in ['status','selected_spans']}
    branches=[]
    for status in ['answered','insufficient_evidence']:
        properties=deepcopy(schema['properties'])
        properties['status']={'type':'string','const':status}
        if status=='answered':properties['selected_spans']['minItems']=1
        else:properties['selected_spans']['maxItems']=0
        branches.append({'type':'object','properties':properties,'required':['status','selected_spans'],'additionalProperties':False})
    schema['oneOf']=branches
    return schema


def quoted_narrative(points):
    return 'The retrieved sources state:\n\n'+'\n\n'.join(point.text for point in points)


def source_caveats(evidence,citations):
    caveats=[];seen=set()
    for item in evidence:
        c=item.chunk
        if c.id not in citations or c.source_id in seen:continue
        seen.add(c.source_id)
        details=[]
        if c.scope:details.append('Scope: '+c.scope)
        if c.limitations:details.append('Limitations: '+c.limitations)
        if details:caveats.append(c.title+' — '+' '.join(details))
    return caveats


def assemble_answer(selection,spans,evidence):
    lookup={s.alias:s for s in spans}
    if any(alias not in lookup for alias in selection.selected_spans):
        raise ValueError('The model selected a span that was not supplied.')
    selected=list(dict.fromkeys(selection.selected_spans))
    if bool(selected)!=(selection.status=='answered'):
        raise ValueError('Answer status and selected evidence are inconsistent.')
    if not selected:
        followups=[]
        if evidence:
            chunk=evidence[0].chunk
            followups=[f'What does "{chunk.title}" say in the "{chunk.section}" section?']
        return ResearchAnswer(status='insufficient_evidence',answer_style='source_quotes',
            answer='I could not answer that exact question from the retrieved passages. You can inspect the sources below or try the narrower question.',key_points=[],citations=[],
            caveats=['This is a model abstention, not proof that the information is absent.'],follow_up_questions=followups)
    points=[]
    quote_positions={}
    sources={item.chunk.id:item.chunk.source_id for item in evidence}
    for alias in selected:
        span=lookup[alias]
        canonical_text=re.sub(r'^AND\s+','',span.text,flags=re.IGNORECASE)
        identity=(sources[span.citation],span.field,canonical_text.casefold())
        point=KeyPoint(text=span.text,citations=[span.citation],
            supporting_quotes=[EvidenceQuote(citation=span.citation,field=span.field,quote=span.text)])
        if identity in quote_positions:
            position=quote_positions[identity]
            if points[position].text.startswith('AND ') and not point.text.startswith('AND '):
                points[position]=point
            continue
        quote_positions[identity]=len(points)
        points.append(point)
    citations=list(dict.fromkeys(p.citations[0] for p in points))
    return ResearchAnswer(status='answered',answer_style='source_quotes',answer=quoted_narrative(points),
        key_points=points,citations=citations,caveats=source_caveats(evidence,citations),follow_up_questions=[])
