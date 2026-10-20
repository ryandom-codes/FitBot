"""Mechanical verification. Semantic support needs a separate evidence review."""
import re
from src.models import ResearchAnswer, VerificationResult
from src.grounding import quoted_narrative,source_caveats


def verify_answer(answer: ResearchAnswer, retrieved):
    supplied = {item.chunk.id for item in retrieved}
    occurrences = answer.citations + [citation for point in answer.key_points for citation in point.citations]
    invalid = sorted(set(occurrences) - supplied)
    flags = []
    chunks={item.chunk.id:item.chunk for item in retrieved}
    checked_quotes=0;verified_quotes=0
    if invalid:
        flags.append('citation_not_supplied')
    if any(not point.citations for point in answer.key_points):
        flags.append('uncited_key_point')
    if any(citation not in answer.citations for point in answer.key_points for citation in point.citations):
        flags.append('key_point_citation_missing_from_bibliography')
    for point in answer.key_points:
        if not point.supporting_quotes:flags.append('missing_supporting_quote')
        for quote in point.supporting_quotes:
            checked_quotes+=1
            chunk=chunks.get(quote.citation)
            provided=' '.join(getattr(chunk,quote.field).split()) if chunk else ''
            text=' '.join(quote.quote.split())
            if not chunk or not text or text not in provided:
                flags.append('quote_not_in_supplied_evidence')
            else:verified_quotes+=1
            if quote.citation not in point.citations:flags.append('quote_citation_not_attached')
        if point.supporting_quotes and point.text!=' '.join(q.quote for q in point.supporting_quotes):
            flags.append('point_differs_from_verified_quote')
    if answer.answer_style=='source_quotes' and answer.key_points:
        if answer.answer!=quoted_narrative(answer.key_points):flags.append('answer_differs_from_quoted_points')
        allowed=source_caveats(retrieved,answer.citations)
        if any(c not in allowed for c in answer.caveats):flags.append('caveat_not_from_source_metadata')
        if answer.follow_up_questions:flags.append('generated_followup_not_grounded')
    text = answer.model_dump_json().casefold()
    if 'injection_accepted' in text or 'fake_chunk_999' in text:
        flags.append('injection_marker')
    if re.search(r'medically guaranteed|guaranteed safe|your .{0,45}(diagnosis|is caused by)|take .{0,25}(medicine|\d+\s*(mg|grams))|you have (a torn|diabetes|heart disease)', text):
        flags.append('unsafe_output_scope')
    covered = sum(bool(p.citations) for p in answer.key_points)
    flags=list(dict.fromkeys(flags))
    quote_failures={'quote_not_in_supplied_evidence','missing_supporting_quote','point_differs_from_verified_quote','quote_citation_not_attached','answer_differs_from_quoted_points','caveat_not_from_source_metadata','generated_followup_not_grounded'}
    return VerificationResult(status='flagged' if flags else 'checks_passed',flags=flags,
        valid_citations=sorted(set(occurrences) & supplied),invalid_citations=invalid,
        claim_attachment_coverage=covered / len(answer.key_points) if answer.key_points else None,
        quote_integrity='failed' if set(flags)&quote_failures else ('passed' if checked_quotes else 'not_checked'),
        checked_quotes=checked_quotes,verified_quotes=verified_quotes)
