"""Occurrence-scoped numeric evidence. Source strings are data, never instructions."""
from collections import Counter
import json
import re
from urllib.parse import urlsplit
from .contracts import require, issue

POLICY = 'career-agent.numeric-occurrences/1'
EXTERNAL = frozenset(('resume', 'message', 'answers'))
NUMBER = re.compile(r'(?<!\d)[+\-−]?\d+(?:[.,]\d+)*')
IDENTIFIER = re.compile(r'(?<!\w)[^\W_]+(?:[._-][^\W_]+)*(?!\w)')
# Measurement grammar, not a list of brands. Bare equal values never grant reuse.
UNITS = (
    ('percent', r'%|percent(?:age)?s?|процент(?:а|ов)?'),
    ('USD', r'USD|US\$|\$'), ('EUR', r'EUR|€'), ('GBP', r'GBP|£'),
    ('ms', r'milliseconds?|ms|миллисекунд(?:а|ы)?|мс'),
    ('s', r'seconds?|secs?|секунд(?:а|ы)?'),
    ('min', r'minutes?|mins?|минут(?:а|ы)?'),
    ('h', r'hours?|hrs?|час(?:а|ов)?'),
    ('year', r'years?|yrs?|год(?:а)?|лет'),
    ('engineer', r'engineers?|инженер(?:а|ов)?'),
    ('person', r'people|persons?|человек(?:а)?'),
    ('inch', r'inches|inch'), ('cm', r'centimeters?|cm'), ('mm', r'millimeters?|mm'),
)


def quantity_unit(text, match):
    following = text[match.end():match.end()+40]
    if following.lstrip().startswith('%'):return 'percent'
    before = text[max(0, match.start()-12):match.start()]
    for unit, pattern in UNITS:
        if re.match(r'\s*(?:'+pattern+r')(?![^\W\d_])', following, re.IGNORECASE): return unit
        if unit in ('USD','EUR','GBP') and re.search(r'(?<!\w)(?:'+pattern+r')\s*$', before, re.IGNORECASE): return unit
    if re.match(r'\s*[x×](?!\w)', following) or re.search(r'(?<!\w)[x×]$', before): return 'multiplier'
    return None


def candidates(text):
    for match in IDENTIFIER.finditer(text):
        token = match.group()
        if len(token)<=128 and any(char.isalpha() for char in token) and any(char.isdigit() for char in token): yield match


def reference_index(entities=(), sources=(), declared=()):
    """Canonical identity is automatic; an agent declares source-backed reference meaning once."""
    result = {}
    for entity in entities:
        for value in (entity.get('name',''), entity.get('domain') or ''):
            for match in candidates(value):
                result.setdefault(match.group().casefold(), dict(text=match.group(), kind='company', record_id=entity['id'], record_version=entity['version']))
    require(isinstance(declared,(list,tuple)) and len(declared)<=100,'INVALID_REVIEW','Entity references must be bounded')
    by_source={source['id']:source for source in sources}
    for entry in declared:
        require(isinstance(entry,dict) and set(entry)=={'text','source_id'},'INVALID_REVIEW','Entity reference requires text/source_id')
        value=entry['text'];source=by_source.get(entry['source_id'])
        require(isinstance(value,str) and len(value)<=128 and IDENTIFIER.fullmatch(value) and any(c.isalpha() for c in value) and any(c.isdigit() for c in value),
                'INVALID_REVIEW','Entity reference must name one complete alphanumeric identifier')
        require(source and source['readable'] and source['excerpt'].strip(),'ENTITY_REFERENCE_UNVERIFIED','Entity reference needs scoped readable evidence')
        values=[source['excerpt']]
        parsed=urlsplit(source['locator'])
        if parsed.scheme in ('http','https') and parsed.hostname:values.append(parsed.hostname.removeprefix('www.'))
        require(any(match.group().casefold()==value.casefold() for text in values for match in candidates(text)),
                'ENTITY_REFERENCE_UNVERIFIED','Entity reference must occur literally in its saved source')
        require(not any(quantity_unit(value,number) for number in NUMBER.finditer(value)),
                'INVALID_REVIEW','A source measurement cannot become a reference exception')
        result.setdefault(value.casefold(),dict(text=value,kind='source',record_id=source['id'],record_version=source['version']))
    return result


def occurrences(text, references=None):
    references = references or {}
    identifiers=list(candidates(text));cursor=0;result=[]
    for match in NUMBER.finditer(text):
        while cursor<len(identifiers) and identifiers[cursor].end()<=match.start(): cursor+=1
        token=identifiers[cursor] if cursor<len(identifiers) and identifiers[cursor].start()<=match.start() and identifiers[cursor].end()>=match.end() else None
        unit=quantity_unit(text,match)
        reference=references.get(token.group().casefold()) if token else None
        # Signed values, decimals, measurements and multipliers keep their quantitative role.
        quantitative=unit is not None
        role='reference' if reference and not quantitative else 'quantity'
        result.append(dict(text=match.group(),start=match.start(),end=match.end(),role=role,unit=unit,
                           **dict(reference=reference,entity_start=token.start(),entity_end=token.end()) if role=='reference' else {}))
        require(len(result)<=2048, 'LIMIT_EXCEEDED', 'Numeric occurrences exceed the bounded review limit')
    return result


def number_tokens(text):
    """Raw numeric values; role resolution requires scoped evidence, never global exceptions."""
    return [entry['text'] for entry in occurrences(text)]


def _key(entry): return entry['text'], entry['unit']


def explicit_entities(documents, review, references, sources, entities):
    """Optional agent disambiguation of exact identifiers; quantities cannot be relabeled wholesale."""
    spans = review.get('entity_spans', [])
    require(isinstance(spans,list) and len(spans)<=100, 'INVALID_REVIEW', 'Entity spans must be bounded')
    result=[];by_slot={doc['slot']:doc['text'] for doc in documents};by_source={source['id']:source for source in sources};by_entity={entity['id']:entity for entity in entities}
    for span in spans:
        require(isinstance(span,dict) and set(span) in ({'slot','start','end','text','source_id'},{'slot','start','end','text','company_id'}), 'INVALID_REVIEW', 'Entity span requires slot/start/end/text and one existing source/company reference')
        start,end=span['start'],span['end'];value=span['text'];text=by_slot.get(span['slot'])
        require(type(start) is int and type(end) is int and isinstance(value,str) and text is not None and 0<=start<end<=len(text) and text[start:end]==value,
                'INVALID_REVIEW', 'Entity span must bind exact saved document text')
        require(IDENTIFIER.fullmatch(value) and any(c.isalpha() for c in value) and any(c.isdigit() for c in value), 'INVALID_REVIEW', 'Entity span must cover one complete alphanumeric identifier')
        require(any(token.start()==start and token.end()==end for token in candidates(text)), 'INVALID_REVIEW', 'Entity span cannot hide part of a larger token')
        if 'source_id' in span:
            source=by_source.get(span['source_id'])
            require(source and source['readable'] and source['excerpt'].strip() and any(match.group().casefold()==value.casefold() for match in candidates(source['excerpt'])),
                    'ENTITY_REFERENCE_UNVERIFIED', 'Entity span needs its scoped readable literal source')
            ref=dict(text=value,kind='source',record_id=source['id'],record_version=source['version'])
            require(not any(quantity_unit(value,m) for m in NUMBER.finditer(value)), 'INVALID_REVIEW', 'A source measurement cannot be relabeled as an entity')
        else:
            entity=by_entity.get(span['company_id'])
            require(entity and any(match.group().casefold()==value.casefold() for field in (entity['name'],entity.get('domain') or '') for match in candidates(field)), 'ENTITY_REFERENCE_UNVERIFIED', 'Entity span needs an exact canonical company identifier')
            ref=dict(text=value,kind='company',record_id=entity['id'],record_version=entity['version'])
        for number in NUMBER.finditer(text):
            if start<=number.start() and number.end()<=end and quantity_unit(text,number):
                local=list(NUMBER.finditer(value))
                require('company_id' in span and all(quantity_unit(value,item) for item in local), 'INVALID_REVIEW', 'An external measurement marker cannot be hidden by an entity span')
        result.append(dict(slot=span['slot'],start=start,end=end,reference=ref))
    return result


def numeric_review(documents, claims, review, answers=(), entities=(), sources=()):
    """Each permitted quantity belongs to its actual mapped claim/value range, not to a global set."""
    references=reference_index(entities,sources,review.get('entity_refs',[]));overrides=explicit_entities(documents,review,references,sources,entities)
    docs={doc['slot']:doc['text'] for doc in documents if doc['slot'] in EXTERNAL}
    indexed={slot:occurrences(text,references) for slot,text in docs.items()};supported=set();by_claim={claim['id']:claim for claim in claims}
    require(sum(len(entries) for entries in indexed.values())<=2048,'LIMIT_EXCEEDED','Numeric packet audit exceeds its bound')
    for span in overrides:
        for entry in indexed.get(span['slot'],[]):
            if span['start']<=entry['start'] and entry['end']<=span['end']:
                entry.update(role='reference',unit=None,reference=span['reference'],entity_start=span['start'],entity_end=span['end'])
    for span in review['claim_spans']:
        claim=by_claim[span['claim_id']];wording=span['text']
        budgets=[]
        for value in (claim['assertion'],claim['meaning']):budgets.append(Counter(_key(n) for n in occurrences(value,references) if n['role']=='quantity'))
        budget=budgets[0]|budgets[1]
        for slot,text in docs.items():
            start=text.find(wording)
            while start>=0:
                available=budget.copy()
                for entry in indexed[slot]:
                    if entry['role']=='quantity' and start<=entry['start'] and entry['end']<=start+len(wording) and available[_key(entry)]:
                        available[_key(entry)]-=1;supported.add((slot,entry['start'],entry['end']))
                start=text.find(wording,start+len(wording))
    # Contact values are exact literal occurrences. An unrelated equal digit does not reuse a phone/email.
    for answer in answers:
        if not answer['meaning'].startswith(('contact.','compensation.external')) or answer['disposition']!='answered': continue
        value=answer['value']
        if isinstance(value,str):
            try:value=json.loads(value)
            except ValueError:pass
        literals=[value] if isinstance(value,str) else [item for item in value.values() if isinstance(item,str)] if isinstance(value,dict) else []
        for value in literals:
            if not value or len(value)>512:continue
            # Scalar short numeric responses need a field-bound span, not a packet-wide number grant.
            if re.fullmatch(r'[\d.,+\-−\s]+',value) and sum(c.isdigit() for c in value)<7:continue
            for slot,text in docs.items():
                start=text.find(value)
                while start>=0:
                    for entry in indexed[slot]:
                        if start<=entry['start'] and entry['end']<=start+len(value) and entry['unit'] is None: supported.add((slot,entry['start'],entry['end']))
                    start=text.find(value,start+len(value))
    # Phone formatting can vary without changing the exact current scoped number.
    for answer in answers:
        if not answer['meaning'].startswith('contact.phone') or answer['disposition']!='answered':continue
        value=answer['value']
        if isinstance(value,str):
            try:value=json.loads(value)
            except ValueError:pass
        values=[value] if isinstance(value,str) else [item for item in value.values() if isinstance(item,str)] if isinstance(value,dict) else []
        digits={''.join(char for char in value if char.isdigit()) for value in values if 7<=sum(char.isdigit() for char in value)<=20}
        for slot,text in docs.items():
            for match in re.finditer(r'(?<!\w)\+?\d[\d ()+.-]{5,38}\d(?!\w)',text):
                if ''.join(char for char in match.group() if char.isdigit()) not in digits:continue
                for entry in indexed[slot]:
                    if match.start()<=entry['start'] and entry['end']<=match.end() and entry['unit'] is None:supported.add((slot,entry['start'],entry['end']))
    answer_spans=review.get('answer_spans',[])
    require(isinstance(answer_spans,list) and len(answer_spans)<=100,'INVALID_REVIEW','Answer spans must be bounded')
    by_answer={answer['id']:answer for answer in answers}
    for span in answer_spans:
        require(isinstance(span,dict) and set(span)=={'answer_id','text'} and isinstance(span['text'],str) and span['text'], 'INVALID_REVIEW', 'Answer span requires answer_id/text')
        answer=by_answer.get(span['answer_id'])
        require(answer and answer['disposition']=='answered' and answer['meaning'].startswith(('contact.','compensation.external')), 'UNSUPPORTED_ANSWER', 'Numeric answer span requires an applicable actual external response')
        raw=answer['value']
        if isinstance(raw,str):
            try:raw=json.loads(raw)
            except ValueError:pass
        units=answer.get('units',{})
        if isinstance(units,str):
            try:units=json.loads(units)
            except ValueError:units={}
        values=[raw] if isinstance(raw,(str,int,float)) else list(raw.values()) if isinstance(raw,dict) else []
        source=' '.join(str(value) for value in values)
        allowed=Counter(_key(entry) for entry in occurrences(source) if entry['role']=='quantity')
        currency=units.get('currency') if isinstance(units,dict) else None
        if currency in ('USD','EUR','GBP'):
            allowed=Counter((value,unit or currency) for value,unit in allowed.elements())
        found=False
        for slot,text in docs.items():
            start=text.find(span['text'])
            while start>=0:
                found=True;available=allowed.copy()
                for entry in indexed[slot]:
                    if start<=entry['start'] and entry['end']<=start+len(span['text']) and available[_key(entry)]:
                        available[_key(entry)]-=1;supported.add((slot,entry['start'],entry['end']))
                start=text.find(span['text'],start+len(span['text']))
        require(found,'UNSUPPORTED_ANSWER','Answer span must bind actual external text')
    issues=[];audit=[]
    for slot,entries in indexed.items():
        for entry in entries:
            audit.append(dict(slot=slot,supported=entry['role']=='reference' or (slot,entry['start'],entry['end']) in supported,**entry))
            if entry['role']=='quantity' and (slot,entry['start'],entry['end']) not in supported:
                issues.append(dict(issue('UNMATCHED_NUMBER','Unmatched numerical assertion: '+entry['text']),slot=slot,start=entry['start'],end=entry['end'],token=entry['text'],role='quantity',unit=entry['unit'],offset_unit='unicode_code_points'))
    return issues,dict(policy=POLICY,offset_unit='unicode_code_points',occurrences=audit)
