"""Bounded allowlisted HTML refresh; review changes before using a new corpus.

Raw HTML is stored outside the public project. No recursive crawling or answer-time browsing.
"""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 2_000_000


def extract_markdown_section(markdown, heading):
    lines = markdown.splitlines()
    start = next((i for i,line in enumerate(lines) if re.match(r'^#{1,4} ',line) and line.lstrip('# ').strip()==heading),None)
    if start is None:
        raise ValueError(f'Reviewed heading missing: {heading}')
    level = len(lines[start])-len(lines[start].lstrip('#'))
    selected=[]
    for line in lines[start+1:]:
        match=re.match(r'^(#{1,4}) ',line)
        if match and len(match.group(1))<=level: break
        if match: continue
        if line.strip() and not line.strip().startswith(('#','|','Full size','Table ')):
            selected.append(re.sub(r'^\s*[-*] ', '',line).strip())
    return '\n\n'.join(selected)


def extract_section(html: str, heading: str, include_table_rows: bool = False) -> str:
    soup = BeautifulSoup(html, 'html.parser')
    for bad in soup(['script', 'style', 'nav', 'footer', 'aside']):
        bad.decompose()
    target = next((h for h in soup.find_all(['h1','h2','h3','h4']) if ' '.join(h.get_text(' ', strip=True).split()) == heading), None)
    if target is None:
        raise ValueError(f'Reviewed heading missing: {heading}')
    level = int(target.name[1])
    paragraphs = []
    for node in target.find_all_next():
        if node.name in ('h1','h2','h3','h4') and int(node.name[1]) <= level:
            break
        if node.name in ('p','li') and not node.find_parent(['p','li','table']):
            text = ' '.join(node.get_text(' ', strip=True).split())
            if text:
                paragraphs.append(text)
        elif include_table_rows and node.name == 'tr':
            cells=node.find_all(['th','td'],recursive=False)
            text=' | '.join(' '.join(cell.get_text(' ',strip=True).split()) for cell in cells)
            if text:
                paragraphs.append(text)
    if not paragraphs:
        raise ValueError(f'Reviewed heading has no text: {heading}')
    return '\n\n'.join(paragraphs)


SOURCES = [
 dict(source_id='cdc_adult_activity', title='Adult Activity: An Overview', url='https://www.cdc.gov/physical-activity-basics/guidelines/adults.html', published_date='2023-12-20', topic='exercise', sections=['Recommendations for adults'], license='CDC public domain with reuse requirements', policy_url='https://www.cdc.gov/other/agencymaterials.html'),
 dict(source_id='cdc_activity_counts', title='What Counts as Physical Activity for Adults', url='https://www.cdc.gov/physical-activity-basics/adding-adults/what-counts.html', published_date='2023-12-06', topic='strength', section_topics={'Aerobic activity - what counts?':'cardio'}, sections=['Muscle strengthening - what counts?', 'Aerobic activity - what counts?'], license='CDC public domain with reuse requirements', policy_url='https://www.cdc.gov/other/agencymaterials.html'),
 dict(source_id='cdc_intensity', title='How to Measure Physical Activity Intensity', url='https://www.cdc.gov/physical-activity-basics/measuring/index.html', published_date='2025-12-04', topic='cardio', sections=['Measuring physical activity intensity'], license='CDC public domain with reuse requirements', policy_url='https://www.cdc.gov/other/agencymaterials.html'),
 dict(source_id='niddk_adult_food', title='Health Tips for Adults', url='https://www.niddk.nih.gov/health-information/weight-management/healthy-eating-physical-activity-for-life/health-tips-for-adults', published_date='2020-09', topic='nutrition', sections=['Consuming Healthy Food and Beverages'], license='NIDDK copyright-free text with exceptions', policy_url='https://www.niddk.nih.gov/copyright'),
 dict(source_id='niddk_portions', title='Food Portions: Choosing Just Enough for You', url='https://www.niddk.nih.gov/health-information/weight-management/just-enough-food-portions', published_date='2021-07', topic='nutrition', sections=['What is the difference between a portion and a serving?'], license='NIDDK copyright-free text with exceptions', policy_url='https://www.niddk.nih.gov/copyright'),
 dict(source_id='fda_nutrition_label', title='How to Understand and Use the Nutrition Facts Label', url='https://www.fda.gov/food/nutrition-facts-label/how-understand-and-use-nutrition-facts-label', published_date=None, topic='nutrition', sections=['1. Serving Information', '2. Calories', '4. The Percent Daily Value (%DV)'], license='FDA public domain unless otherwise noted', policy_url='https://www.fda.gov/about-fda/about-website/website-policies'),
    dict(source_id='rt_meta_2026', title='The Influence of Individual Resistance Training Variables on Muscle Strength: A Systematic Review and Meta-analysis', url='https://link.springer.com/article/10.1007/s40279-026-02432-5', published_date='2026-04-17', topic='strength', sections=['2.2 Inclusion and Exclusion Criteria', '3.1 Effect of Resistance Training (RT) on Muscle Strength', '5 Limitations'], license='CC BY 4.0; Lyristakis et al. (2026)', policy_url='https://creativecommons.org/licenses/by/4.0/', doi='10.1007/s40279-026-02432-5'),
 dict(source_id='cdc_sleep', title='About Sleep', url='https://www.cdc.gov/sleep/about/index.html', published_date='2024-05-15', topic='sleep', sections=['Getting enough sleep','What to do'], license='CDC public domain with reuse requirements', policy_url='https://www.cdc.gov/other/agencymaterials.html'),
]


def fetch_html(url: str) -> str:
    request = Request(url, headers={'User-Agent': 'FitnessResearchPortfolio/1.0 (bounded educational snapshot)'})
    with urlopen(request, timeout=30) as response:
        if response.url != url:
            raise ValueError(f'Unexpected redirect requiring review: {response.url}')
        if 'text/html' not in response.headers.get('Content-Type', ''):
            raise ValueError('Expected reviewed HTML source')
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('Source exceeds bounded HTML size')
        return raw.decode('utf-8')


def build_snapshot(raw_dir: Path, *, offline: bool = False, extracted_pages=None) -> dict:
    if ROOT == raw_dir.resolve() or ROOT in raw_dir.resolve().parents:
        raise ValueError('Raw HTML must be stored outside the public project')
    raw_dir.mkdir(parents=True, exist_ok=True)
    accessed = datetime.now(timezone.utc).date().isoformat()
    documents, provenance = [], []
    for source in SOURCES:
        raw_path = raw_dir / f"{source['source_id']}.html"
        html = extracted_pages[source['url']] if extracted_pages else (raw_path.read_text(encoding='utf-8') if offline else fetch_html(source['url']))
        if not offline and not extracted_pages:
            raw_path.write_text(html, encoding='utf-8')
        soup = BeautifulSoup(html, 'html.parser')
        if source['title'].lower() not in html.lower() and source['title'].lower() not in soup.get_text(' ', strip=True).lower():
            raise ValueError('Source title missing; manual review required')
        extractor=extract_markdown_section if extracted_pages else extract_section
        extracted = {heading: (extract_section(html,heading,include_table_rows=True)
                     if source['source_id']=='cdc_sleep' else extractor(html,heading)) for heading in source['sections']}
        research = source['source_id'] == 'rt_meta_2026'
        scope = ('Randomized trials: adults 18+, no current diagnosed medical/musculoskeletal condition; resistance training at least four weeks versus non-exercise control. Concurrent exercise excluded; chest/quadriceps outcomes, predominantly untrained populations.' if research else 'General adult education; not personalized medical or athletic programming.')
        limitations = ('Dosage associations are not mechanistic causal effects. Publication bias and heterogeneity; mainly short-term, untrained populations. Trained versus untrained comparisons could not be made. No individual outcome guarantee.' if research else 'Official educational guidance, not an original experiment or evidence for individual forecasts. Dated snapshot; linked sources and images are excluded.')
        # Exact excerpt subsets keep the initial corpus small. Heading boundaries
        # and complete paragraph selection are recorded in the public manifest.
        for heading, text in extracted.items():
            selection = 'Complete text paragraphs/list items within heading; images, captions and tables omitted.'
            if source['source_id']=='cdc_adult_activity':
                text=text.split('Check out this age chart')[0].strip()
                selection='Adult recommendations and examples through greater-benefit statement; promotional text, images and navigation omitted.'
            if source['source_id']=='niddk_portions':
                text=text.split('Figure 1. Nutrition Facts label')[0].strip()
                selection='Portion/serving definitions and complete two-serving example; figure caption and image omitted.'
            if source['source_id']=='fda_nutrition_label' and heading.startswith('2.'):
                paras=text.split('\n\n')
                text='\n\n'.join(p for p in paras if p.startswith('Calories provide') or p.startswith('Remember:'))
                selection='Energy-per-serving and number-of-servings explanation only; calorie-target/linked meal-planning paragraph omitted.'
            if source['source_id'] == 'niddk_adult_food':
                # Only introductory food-choice paragraph and nutrient-rich examples.
                paras = text.split('\n\n')
                end = next(i for i, p in enumerate(paras) if p.startswith("If you're sensitive") or p.startswith('If you’re sensitive'))
                text = '\n\n'.join(p for p in paras[:end] if not p.startswith('Visit MyPlate'))
                selection = 'Opening food-choice paragraphs and nutrient-rich food list only; subsequent dietary advice, calorie planning, and old numerical targets omitted.'
            if source['source_id'] == 'fda_nutrition_label' and heading.startswith('4.'):
                paras = text.split('\n\n')
                end = next(i for i, p in enumerate(paras) if p.startswith('More often, choose'))
                text = '\n\n'.join(paras[:end])
                selection = 'Initial percent-Daily-Value explanation and low/high reference guide only; later dietary goals and tables omitted.'
            if research and heading == '5 Limitations':
                # Selected complete sentences with explicit omissions, not a rewritten conclusion.
                pieces=[]
                for beginning,end_marker in [('The constructed dosage variable','There are several methodological'),('Second, the utilisation','While permutation'),('Fourth, the findings','Furthermore, other variables'),('Last, trained participants',None)]:
                    begin=text.index(beginning)
                    end=text.index(end_marker,begin) if end_marker else len(text)
                    pieces.append(text[begin:end].strip())
                text='\n\n'.join(pieces)
                selection = 'Selected complete limitation sentences: composite/association warning, publication bias/heterogeneity, short-term untrained scope, and final trained-population data limits. Intervening sentences omitted; full original linked. Compact authored metadata is separately labeled.'
            if research and heading.startswith('2.2'):
                # Omit strength-test instrument detail; preserve all eligibility exclusions.
                text='\n\n'.join([text[:text.index('Dynamic muscle strength')].strip(),text[text.index('Studies not written'):].strip()])
                selection='Eligibility sentence and English/RCT/concurrent-exercise exclusions; test-instrument sentence omitted.'
            if research and heading.startswith('3.1'):
                text=text.replace('Figs. 1\ufffd4','Figs. 1–4')
                selection = 'Complete effect paragraph; study eligibility and selected limitations attached as grounding metadata.'
            topic=source.get('section_topics',{}).get(heading,source['topic'])
            documents.append({k: source.get(k) for k in ('source_id','title','url','published_date','license','doi')} | dict(topic=topic,section=heading,text=text,evidence_type='systematic_review_meta_analysis' if research else ('agency_guidance' if source['source_id']=='cdc_sleep' else 'agency_summary'),accessed_date=accessed,date_label='Published' if research else ('Last Reviewed' if source['source_id'].startswith('niddk') else 'Displayed page date'),scope=scope,limitations=limitations,page=None))
            provenance.append(dict(source_id=source['source_id'], section=heading, selection=selection, extracted_page_sha256=hashlib.sha256(html.encode('utf-8')).hexdigest(), extraction_method='Exa webpage extraction, checked against official page' if extracted_pages else 'Direct official HTML', text_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(), policy_url=source['policy_url'], date_label='Published' if research else ('Last Reviewed' if source['source_id'].startswith('niddk') else 'Displayed page date; not necessarily publication'), evidence_search_end='2025-07-10' if research else None, authors='Lyristakis, Wundersitz, Cousins, Huynh, Zadow, Gordon' if research else None, protocol_url='https://doi.org/10.17605/OSF.IO/EH94V' if research else None, metadata_note='Scope/limitations metadata authored from reviewed source; excerpt text separately preserved. E2 figure-range punctuation checked against official web text.' if research else 'General applicability metadata authored for project.'))
    return dict(snapshot_date=accessed, sources=provenance, documents=documents)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='Write a candidate JSON snapshot for manual review')
    parser.add_argument('--offline', action='store_true', help='Re-extract previously saved private raw HTML')
    parser.add_argument('--extracted-pages',type=Path,help='Private JSON mapping reviewed URLs to extracted Markdown; manually inspect provenance')
    args = parser.parse_args()
    pages=json.loads(args.extracted_pages.read_text(encoding='utf-8')) if args.extracted_pages else None
    snapshot = build_snapshot(args.raw_dir, offline=args.offline,extracted_pages=pages)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"Wrote {len(snapshot['documents'])} candidate sections; manual provenance review required.")


if __name__ == '__main__':
    main()
