"""Pure bounded qualification, scoped policy and mechanical review rules."""
import re
from urllib.parse import urlsplit
from .contracts import issue, require
from .numeric import number_tokens, numeric_review, occurrences, reference_index


def safe_route(kind, value):
    require(kind in ('profile','email','form','website'), 'INVALID_INPUT', 'Unsupported professional route')
    if kind == 'email':
        require(re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value), 'INVALID_INPUT', 'Invalid published email')
    else:
        parsed = urlsplit(value)
        require(parsed.scheme in ('https','http') and parsed.hostname and not parsed.username and not parsed.password,
                'INVALID_INPUT', 'Only ordinary HTTP(S) professional links are allowed')


def contact_issues(person, sources, route, at):
    issues = []
    if person['affiliation'] != 'current':
        issues.append(issue('AFFILIATION_UNKNOWN', 'Current affiliation is not established', person['id']))
    if person.get('valid_until') and person['valid_until'] <= at:
        issues.append(issue('AFFILIATION_EXPIRED', 'Affiliation requires recheck', person['id']))
    for axis in ('identity','affiliation','relevance'):
        observations = [s for s in sources if axis in s['axes']]
        if not any(s['assessment']=='supports' and s['readable'] for s in observations) or any(s['assessment']=='conflicts' for s in observations):
            issues.append(issue('EVIDENCE_GAP', 'Missing or conflicting '+axis+' evidence', person['id']))
    if not route or not route.get('readable') or route.get('suppressed'):
        issues.append(issue('ROUTE_UNVERIFIED', 'No currently usable evidenced professional route', person['id']))
    return issues


def resolve_policy(defaults, overrides, task):
    """Unknown is an explicit override; only inherit falls through."""
    result = {}
    for layer in (defaults, overrides, task):
        for key, value in layer.items():
            require(isinstance(value,dict) and value.get('state') in ('inherit','known','no_preference','unknown'),
                    'INVALID_POLICY', 'Policy values require explicit state')
            if value['state'] != 'inherit':
                result[key] = value
    return result


def mechanical_review(documents, claims, review, answers=(), entities=(), sources=(), numeric_audit=None):
    issues = []
    joined = '\n'.join(d['text'] for d in documents if d['slot'] in ('resume','message','answers'))
    for claim in claims:
        if claim['confirmation'] != 'confirmed' or claim['disclosure'] != 'allowed' or claim['contradicted']:
            issues.append(issue('CLAIM_NOT_REUSABLE','Used claim is unconfirmed, private or disputed',claim['id']))
    if not review:
        return issues + [issue('REVIEW_REQUIRED','Draft requires concrete fact and tone review')]
    require(isinstance(review,dict) and {'findings','limitations','claim_spans','tone_findings','coverage'} <= set(review) <= {'findings','limitations','claim_spans','tone_findings','coverage','base_coverage_version_id','entity_spans','entity_refs','answer_spans','editorial'},
            'INVALID_REVIEW','Review requires findings, limitations, claim_spans, tone_findings and coverage')
    require(review['findings'] and review['tone_findings'] and review['limitations'], 'INVALID_REVIEW','Review must report actual findings and limits')
    mapped = set()
    for span in review['claim_spans']:
        require(isinstance(span,dict) and set(span) == {'claim_id','text'}, 'INVALID_REVIEW','Claim span requires exact claim_id/text')
        claim = next((c for c in claims if c['id']==span['claim_id']), None)
        require(claim is not None and span['text'] and span['text'] in joined,'UNSUPPORTED_CLAIM','Claim span must map an actual external span to a used claim')
        mapped.add(claim['id'])
    for claim in claims:
        if claim['id'] not in mapped:
            issues.append(issue('CLAIM_COVERAGE_GAP','Used claim lacks exact external wording mapping',claim['id']))
    numeric_issues,audit = numeric_review(documents,claims,review,answers,entities,sources)
    issues.extend(numeric_issues)
    if numeric_audit is not None:numeric_audit.update(audit)
    for coverage in review['coverage']:
        require(isinstance(coverage,dict) and 'claim_id' in coverage and coverage.get('disposition') in ('included','condensed','private','excluded','pending'),
                'INVALID_REVIEW','Coverage needs claim_id and supported disposition')
        if coverage['disposition'] in ('excluded','private'):
            require(bool(coverage.get('reason')), 'COVERAGE_GAP','Exclusions require concrete provenance/reason')
        if coverage['disposition']=='pending':
            issues.append(issue('COVERAGE_GAP','Meaningful claim remains unaccounted for',coverage['claim_id']))
    issues.extend(coverage_issues(documents,claims,review,entities,sources))
    return issues


def coverage_issues(documents,claims,review,entities=(),sources=()):
    """Bind audit dispositions to actual source/selected spans; do not infer meaning."""
    issues=[]
    references=reference_index(entities,sources,review.get('entity_refs',[]))
    by_id={claim['id']:claim for claim in claims}
    resume=next((d['text'] for d in documents if d['slot']=='resume'),None)
    external='\n'.join(d['text'] for d in documents if d['slot'] in ('resume','message','answers'))
    for entry in review['coverage']:
        if entry['disposition'] not in ('included','condensed'):continue
        claim=by_id.get(entry['claim_id'])
        spans=[span['text'] for span in review['claim_spans'] if span['claim_id']==entry['claim_id']]
        applicable=resume if resume is not None else external
        actual=[span for span in spans if span and span in applicable]
        if claim is None or not actual:
            issues.append(issue('COVERAGE_SPAN_MISSING','Included/condensed achievement must be a used claim bound to actual applicable resume wording',entry['claim_id']))
            continue
        rendered=' '.join(actual)
        original_numbers={entry['text'] for entry in occurrences(claim['assertion'],references) if entry['role']=='quantity'}
        present_numbers={entry['text'] for entry in occurrences(rendered,references) if entry['role']=='quantity'}
        for number in original_numbers-present_numbers:
            issues.append(issue('METRIC_MISSING','Original numerical span is absent from the selected claim wording: '+number,claim['id']))
        original_entries=[entry for entry in occurrences(claim['assertion'],references) if entry['role']=='quantity']
        present_entries=[entry for entry in occurrences(rendered,references) if entry['role']=='quantity']
        for entry in original_entries:
            if entry['unit'] is not None and any(item['text']==entry['text'] for item in present_entries) and not any(item['text']==entry['text'] and item['unit']==entry['unit'] for item in present_entries):
                issues.append(issue('METRIC_UNIT_MISSING','A source numerical unit is absent or changed in selected wording',claim['id']))

    return issues



def answer_scope_matches(scope,track_ids,case=None):
    """Known scope axes must match; an unresolved axis is never broadened by inference."""
    if scope.get('track_id') and scope['track_id'] not in track_ids:return False
    if 'track_ids' in scope and not set(scope['track_ids'])&set(track_ids):return False
    for key in ('company_id','case_id','opportunity_id'):
        expected=(case['id'] if key=='case_id' else case.get(key)) if case else None
        if scope.get(key) and scope[key]!=expected:return False
    return scope.get('purpose','application') in ('application','external')
