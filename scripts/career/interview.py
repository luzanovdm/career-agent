"""Bounded saved interview dialogue in the existing immutable text-slot owner.

This module never generates questions, confirms applicant facts, performs research,
fetches URLs or starts practice. Legacy text remains a document, not inferred turns.
"""
import json
from urllib.parse import urlsplit
from .contracts import CareerError, identifier, require, text

DIALOGUE_FORMAT = 'career-agent.interview/1'
KINDS = {'question', 'answer', 'note'}
STATUSES = {'outline', 'confirmed', 'unknown', 'hypothesis'}
MAX_TURNS = 100
MAX_REFERENCES = 20
MAX_TEXT_BYTES = 262144


def safe_http_url(value):
    """Only explicit navigable HTTP(S), with no credential or control characters."""
    if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 33 for c in value):
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme in ('http', 'https') and bool(parsed.hostname) and not parsed.username and not parsed.password
    except ValueError:
        return False


def _read_source(source_id, source_lookup, strict):
    try:
        source = source_lookup(source_id)
    except CareerError:
        if strict:
            raise
        return dict(id=source_id, locator=None, observed_at=None, readable=False, available=False)
    readable = bool(source.get('readable') and isinstance(source.get('excerpt'), str) and source['excerpt'].strip())
    if strict:
        require(readable, 'INTERVIEW_SOURCE_UNREADABLE', 'Interview references require a readable saved observation')
    return dict(id=source_id, locator=source.get('locator'), observed_at=source.get('observed_at'),
                readable=readable, available=readable)


def _validate(value, source_lookup, strict):
    require(isinstance(value, dict) and set(value) == {'format', 'turns'} and value.get('format') == DIALOGUE_FORMAT,
            'INVALID_INTERVIEW', 'Interview dialogue requires its declared format and ordered turns')
    turns = value['turns']
    require(isinstance(turns, list) and 1 <= len(turns) <= MAX_TURNS,
            'INVALID_INTERVIEW', 'Interview dialogue requires 1..100 saved turns')
    sources = {}
    for turn in turns:
        require(isinstance(turn, dict) and set(turn) == {'kind', 'text', 'status', 'source_ids', 'terms'},
                'INVALID_INTERVIEW', 'Each turn requires kind, text, status, source_ids and terms')
        require(isinstance(turn['kind'],str) and isinstance(turn['status'],str) and turn['kind'] in KINDS and turn['status'] in STATUSES, 'INVALID_INTERVIEW', 'Unknown saved turn kind or status')
        text(turn['text'], 'Saved interview turn', 32768)
        refs = turn['source_ids']
        require(isinstance(refs, list) and len(refs) <= MAX_REFERENCES and all(isinstance(entry,str) for entry in refs) and len(refs) == len(set(refs)),
                'INVALID_INTERVIEW', 'Turn source IDs must be unique and bounded')
        for source_id in refs:
            identifier(source_id)
            if source_id not in sources:
                sources[source_id] = _read_source(source_id, source_lookup, strict)
        if strict and turn['status'] == 'confirmed':
            require(bool(refs), 'INTERVIEW_EVIDENCE_REQUIRED', 'Confirmed saved content requires an explicit readable observation')
        terms = turn['terms']
        require(isinstance(terms, list) and len(terms) <= MAX_REFERENCES, 'INVALID_INTERVIEW', 'Turn terms must be bounded')
        seen = set()
        for term in terms:
            require(isinstance(term, dict) and set(term) == {'label', 'url', 'source_id'},
                    'INVALID_INTERVIEW', 'A linked term requires label, url and source_id')
            text(term['label'], 'Term label', 250)
            require(term['label'] not in seen, 'INVALID_INTERVIEW', 'Term labels must be unique within a turn')
            seen.add(term['label'])
            identifier(term['source_id'])
            require(term['source_id'] in refs, 'INVALID_INTERVIEW', 'Term observation must belong to the turn source IDs')
            require(safe_http_url(term['url']), 'INVALID_INTERVIEW_LINK', 'Term link must be an explicit safe HTTP(S) URL')
            if strict:
                require(sources[term['source_id']]['locator'] == term['url'], 'INTERVIEW_LINK_NOT_OBSERVED',
                        'Term URL must exactly match its readable saved observation locator')
    return sources


def validate_interview_text(content, source_lookup):
    """Validate explicitly declared JSON dialogue; ordinary saved text returns None.

    No speaker or answer is inferred from legacy headings. A declared malformed
    dialogue is rejected rather than silently accepted as a plain document.
    """
    require(isinstance(content, str) and len(content.encode('utf-8')) <= MAX_TEXT_BYTES,
            'LIMIT_EXCEEDED', 'Interview text exceeds the saved slot byte limit')
    if not content.lstrip().startswith('{'):
        return None
    try:
        value = json.loads(content)
    except (ValueError, RecursionError):
        require(DIALOGUE_FORMAT not in content, 'INVALID_INTERVIEW', 'Declared interview dialogue is invalid JSON')
        return None
    if not isinstance(value, dict):
        return None
    require(not isinstance(value.get('format'),str) or not value['format'].startswith('career-agent.interview/') or value['format']==DIALOGUE_FORMAT, 'INVALID_INTERVIEW', 'Unsupported declared interview format')
    if value.get('format') != DIALOGUE_FORMAT:
        return None
    _validate(value, source_lookup, True)
    return value


def project_interview_slot(slot, source_lookup):
    """Read a selected immutable slot as explicit turns or a whole saved document.

    Source changes make links visibly unavailable. This projection does not hide
    or rewrite the saved text, nor certify a current review of historic content.
    """
    base = dict(slot=slot.get('name', 'interview'), artifact_id=slot['artifact_id'])
    content = slot.get('text')
    if content is None:
        return [dict(base, kind='file', text=None, status=None, sources=[], terms=[])]
    value = None
    if isinstance(content, str) and len(content.encode('utf-8')) <= MAX_TEXT_BYTES and content.lstrip().startswith('{'):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and parsed.get('format') == DIALOGUE_FORMAT:
                value = parsed
        except (ValueError, RecursionError):
            pass
    if value is None:
        return [dict(base, kind='document', text=content, status=None, sources=[], terms=[])]
    try:
        sources = _validate(value, source_lookup, False)
    except (CareerError, TypeError, KeyError, ValueError, RecursionError):
        return [dict(base, kind='document', text=content, status=None, sources=[], terms=[],
                     issues=[dict(code='INVALID_INTERVIEW', message='Saved dialogue cannot be safely projected; original document is retained')])]
    result = []
    for index, turn in enumerate(value['turns']):
        terms = []
        for term in turn['terms']:
            source = sources[term['source_id']]
            available = bool(source['available'] and source['locator'] == term['url'])
            terms.append(dict(term, available=available,
                              limitation=None if available else 'Saved reference is missing, unreadable or no longer matches this URL'))
        result.append(dict(base, index=index, kind=turn['kind'], status=turn['status'], text=turn['text'],
                           source_ids=turn['source_ids'], sources=[sources[key] for key in turn['source_ids']], terms=terms))
    return result


def dialogue_schema():
    """Discoverable saved-document contract; runtime validation owns source binding."""
    def obj(properties):return dict(type='object',additionalProperties=False,required=list(properties),properties=properties)
    term=obj(dict(label=dict(type='string',minLength=1,maxLength=250),url=dict(type='string',description='Exact safe HTTP(S) locator of the readable saved source'),source_id=dict(type='string')))
    turn=obj(dict(kind=dict(enum=sorted(KINDS)),text=dict(type='string',minLength=1,maxLength=32768),status=dict(enum=sorted(STATUSES)),source_ids=dict(type='array',items=dict(type='string'),maxItems=20,uniqueItems=True),terms=dict(type='array',items=term,maxItems=20)))
    return obj(dict(format=dict(const=DIALOGUE_FORMAT),turns=dict(type='array',items=turn,minItems=1,maxItems=100)))
